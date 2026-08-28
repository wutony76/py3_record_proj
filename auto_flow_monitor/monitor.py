"""WebSocket 連線與 tick 迴圈，把 config／dev_log／id_check_client／state 組起來執行。"""

from __future__ import annotations

import asyncio
import json
import ssl

import websockets

from .config import Settings
from .dev_log import DevLogger
from .id_check_client import IdCheckClient
from .logging_setup import log
from .signing import make_req_id
from .state import AutoFlowState


def _build_ssl_context() -> ssl.SSLContext:
    """伺服器使用自簽憑證，略過 SSL 驗證。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class AutoFlowMonitor:
    def __init__(self, region_id: int, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.region_id = region_id
        self._ssl_ctx = _build_ssl_context()

        dev_logger = DevLogger(self.settings.dev_log_url, timeout=self.settings.dev_log_timeout_s)
        id_check_client = IdCheckClient(
            api_base=self.settings.api_base,
            secret=self.settings.id_check_secret,
            cmd=self.settings.id_check_cmd,
            dev_logger=dev_logger,
            timeout=self.settings.id_check_timeout_s,
        )
        self.state = AutoFlowState(
            region_id=region_id,
            id_check_client=id_check_client,
            dev_logger=dev_logger,
            ready_status=self.settings.ready_status,
            trigger_before_work_s=self.settings.trigger_before_work_s,
            max_id_check_retry=self.settings.max_id_check_retry,
            retry_backoff_s=self.settings.retry_backoff_s,
        )

    async def _tick_loop(self) -> None:
        while True:
            try:
                await self.state.tick()
            except Exception:
                log.exception("tick() 發生未預期例外，略過本次繼續監控")
            await asyncio.sleep(self.settings.tick_interval_s)

    async def run(self) -> None:
        asyncio.create_task(self._tick_loop())

        while True:
            try:
                log.info(f"連線中... {self.settings.ws_url}")
                async with websockets.connect(
                    self.settings.ws_url, ping_interval=20, ssl=self._ssl_ctx
                ) as ws:
                    # 連線後送 monitor-ping（握手）
                    await ws.send(json.dumps({"wsCmd": "monitor-ping", "reqId": make_req_id()}))
                    log.info("已連線，送出 monitor-ping")

                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        ws_code = msg.get("wsCode", "")
                        if ws_code in ("ws_100002", "ws_100003"):
                            log.debug(f"收到封包 wsCode={ws_code}")
                            self.state.on_ws_packet(msg)

            except Exception as e:
                log.warning(f"WebSocket 斷線: {e}，{self.settings.reconnect_delay_s}s 後重連")
                await asyncio.sleep(self.settings.reconnect_delay_s)

"""
auto_flow_monitor.py
────────────────────
仿照 staffpilot AutoFlowMonitorView 邏輯的獨立 Python 腳本。

功能：
  1. 連線 EMS WebSocket（ws_100002 監台看板）
  2. 解析 empInfoList，找出 status ∈ {1, 11} 的即將上崗人員
  3. 每 500ms 判斷是否到達觸發時間（nextWorkInfo.workTime - 7 分）
  4. 到達時呼叫 idCheck API（MD5 簽名）完成自動刷門
  5. 成功後將該 loginId 記入 desk dict，不再重複打

使用：
  pip install websockets requests
  python auto_flow_monitor.py --region 37
"""

import argparse
import asyncio
import hashlib
import json
import logging
import random
import ssl
import time
import uuid
from datetime import datetime
from typing import Optional

import requests
import urllib3
import websockets

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 伺服器使用自簽憑證，略過 SSL 驗證
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# ─── 設定 ────────────────────────────────────────────────
WS_URL = "wss://api.js-yichang.com/ems/ws"
API_BASE = "https://api.js-yichang.com/ems/api"
DEV_LOG_URL = "http://127.0.0.1:8000/api/log"   # py3_record_proj 本地紀錄
ID_CHECK_SECRET = "p97*kf&56re#^"
ID_CHECK_CMD = "idCheck"
TRIGGER_BEFORE_WORK_S = 7 * 60   # 上崗前 7 分鐘觸發
TICK_INTERVAL_S = 0.5             # 每 500ms 一次 tick
RECONNECT_DELAY_S = 5             # 斷線重連等待秒
READY_STATUS = {1, 11}            # 可觸發的 status 值

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("auto-flow")


# ─── 本地 log 紀錄 ───────────────────────────────────────
def dev_log(tag: str, anal: str, data: dict):
    """非同步送到 py3_record_proj /api/log，失敗靜默。"""
    try:
        requests.post(
            DEV_LOG_URL,
            json={
                "tag": tag,
                "anal": anal,
                "data": data,
                "screenshot": False,
            },
            timeout=3,
        )
    except Exception:
        pass


# ─── 工具函式 ────────────────────────────────────────────
def make_req_id() -> str:
    return uuid.uuid4().hex


def sign_id_check(login_id: str, ts: str) -> str:
    raw = f"{login_id}{ts}{ID_CHECK_SECRET}{ID_CHECK_CMD}"
    return hashlib.md5(raw.encode()).hexdigest()


def parse_worktime(work_time: Optional[str]) -> Optional[float]:
    """把後端 workTime 字串解析成 Unix timestamp (ms)。"""
    if not work_time:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(work_time.split(".")[0], fmt).timestamp() * 1000
        except ValueError:
            continue
    return None


def now_ms() -> float:
    return time.time() * 1000


# ─── idCheck API ────────────────────────────────────────
def id_check(login_id: str) -> dict:
    ts = str(int(now_ms()))
    req_id = make_req_id()
    payload = {
        "channel": "bg",
        "clientType": 1,
        "reqId": req_id,
        "identity": req_id,
        "version": "1.0",
        "cmd": ID_CHECK_CMD,
        "loginId": login_id,
        "sign": sign_id_check(login_id, ts),
        "ts": ts,
    }
    url = f"{API_BASE}/{ID_CHECK_CMD}"
    dev_log(
        tag="py3-monitor",
        anal=f"發起 idCheck: {login_id}",
        data={"loginId": login_id, "ts": ts, "reqId": req_id},
    )
    print(f"[idCheck] → POST {url}")
    print(f"  loginId  : {login_id}")
    resp = requests.post(
        url,
        json=payload,
        timeout=10,
        headers={"Content-Type": "application/json"},
        verify=False,
    )
    resp.raise_for_status()
    envelope = resp.json()
    code = envelope.get("code")
    msg  = envelope.get("message", "")
    data = envelope.get("data") or {}
    if not envelope or code != 0:
        dev_log(
            tag="py3-monitor",
            anal=f"idCheck 失敗: {login_id}",
            data={"loginId": login_id, "code": code, "message": msg},
        )
        raise RuntimeError(f"idCheck 失敗: code={code} msg={msg}")
    return data


# ─── 核心狀態機 ─────────────────────────────────────────
class AutoFlowState:
    def __init__(self, region_id: str):
        self.region_id = region_id
        self.data_time: Optional[str] = None
        self.ready_list: list[str] = []   # 待處理的 loginId
        self.check: dict[str, bool] = {}  # 本 dataTime 已嘗試過的 loginId
        self.desk: dict[str, str] = {}    # 已成功刷門的 loginId → dataTime
        self.info: dict[str, dict] = {}   # loginId → empInfoList item
        self.jumping = False              # 防止 tick 重入

    def on_ws_packet(self, res: dict):
        ws_code = res.get("wsCode", "")
        if ws_code not in ("ws_100002", "ws_100003"):
            return

        data_list = res.get("data", [])
        if not isinstance(data_list, list):
            data_list = [data_list]

        _data = next(
            (d for d in data_list
             if d.get("regionInfo", {}).get("regionId") == int(self.region_id)),
            None,
        )
        if not _data:
            log.debug(f"regionId={self.region_id} 不在本次封包中")
            return

        # dataTime 更新 → 重置 check，允許同一批人重試
        if _data.get("dataTime") and _data["dataTime"] != self.data_time:
            self.data_time = _data["dataTime"]
            self.check = {}
            log.info(f"dataTime 更新: {self.data_time}，check 已重置")

        # 快取 empInfoList（ws_100003 補充人員資料）
        for item in _data.get("empInfoList", []):
            self.info[item["loginId"]] = item

        # 篩出 status ∈ {1, 11}
        ready = [
            item["loginId"]
            for item in _data.get("empInfoList", [])
            if item.get("status") in READY_STATUS
        ]
        if ready:
            existing = set(self.ready_list)
            new_ids = [lid for lid in ready if lid not in existing]
            self.ready_list.extend(new_ids)
            log.info(f"ready_list 新增: {new_ids}  總計: {self.ready_list}")

    async def tick(self):
        """每 500ms 執行一次，判斷是否需要打 idCheck。"""
        if self.jumping:
            return
        if not self.data_time or not self.ready_list:
            return

        all_info = self.info
        checked = {lid for lid, ok in self.check.items() if ok}
        pending = [lid for lid in self.ready_list if lid not in checked]

        if not pending:
            return

        self.jumping = True
        tasks = []
        for login_id in pending:
            item = all_info.get(login_id)
            if not item:
                continue

            next_work_time = item.get("nextWorkInfo", {}).get("workTime")
            trigger_ts = (parse_worktime(next_work_time) or float("nan")) - TRIGGER_BEFORE_WORK_S * 1000

            import math
            if math.isnan(trigger_ts) or now_ms() <= trigger_ts:
                continue

            # 已成功刷門 → 標 check，跳過
            if login_id in self.desk:
                self.check[login_id] = True
                continue

            # 本 dataTime 已嘗試過
            self.check[login_id] = True
            tasks.append(self._do_id_check(login_id))

        if tasks:
            await asyncio.gather(*tasks)

        self.jumping = False

    async def _do_id_check(self, login_id: str):
        log.info(f"▶ 發起 idCheck: {login_id}")
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, id_check, login_id)
            self.desk[login_id] = self.data_time
            log.info(f"✓ idCheck 成功: {login_id}  target={result.get('target')}")
            dev_log(
                tag="py3-monitor",
                anal=f"✓ 刷門成功: {login_id}",
                data={"loginId": login_id, "target": result.get("target"), "dataTime": self.data_time, **result},
            )
        except Exception as err:
            log.warning(f"✗ idCheck 失敗: {login_id}  err={err}")
            dev_log(
                tag="py3-monitor",
                anal=f"✗ 刷門失敗: {login_id}",
                data={"loginId": login_id, "error": str(err), "dataTime": self.data_time},
            )


# ─── WebSocket 主循環 ────────────────────────────────────
async def run(region_id: str):
    state = AutoFlowState(region_id)

    async def tick_loop():
        while True:
            await state.tick()
            await asyncio.sleep(TICK_INTERVAL_S)

    asyncio.create_task(tick_loop())

    while True:
        try:
            log.info(f"連線中... {WS_URL}")
            async with websockets.connect(WS_URL, ping_interval=20, ssl=_SSL_CTX) as ws:
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
                        state.on_ws_packet(msg)

        except Exception as e:
            log.warning(f"WebSocket 斷線: {e}，{RECONNECT_DELAY_S}s 後重連")
            await asyncio.sleep(RECONNECT_DELAY_S)


# ─── 入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoFlow Monitor")
    parser.add_argument("--region", default="37", help="regionId（預設 37）")
    args = parser.parse_args()

    log.info(f"AutoFlow Monitor 啟動  regionId={args.region}")
    asyncio.run(run(args.region))

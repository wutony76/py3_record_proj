"""核心狀態機：追蹤 ready 名單、觸發時間、重試狀態，並發起 idCheck。"""

from __future__ import annotations

import asyncio
from typing import Optional

from .dev_log import DevLogger
from .id_check_client import IdCheckClient
from .logging_setup import log
from .status import compute_status
from .time_utils import now_ms, parse_worktime


class AutoFlowState:
    def __init__(
        self,
        region_id: int,
        id_check_client: IdCheckClient,
        dev_logger: DevLogger,
        ready_status: frozenset = frozenset({1, 11}),
        trigger_before_work_s: int = 3 * 60,
        max_id_check_retry: int = 3,
        retry_backoff_s: int = 10,
    ):
        self.region_id = region_id
        self.id_check_client = id_check_client
        self.dev_logger = dev_logger
        self.ready_status = ready_status
        self.trigger_before_work_s = trigger_before_work_s
        self.max_id_check_retry = max_id_check_retry
        self.retry_backoff_s = retry_backoff_s

        self.data_time: Optional[str] = None
        self.ready_list: list[str] = []        # 待處理的 loginId
        self.desk: dict[str, str] = {}         # 已成功刷門的 loginId → dataTime
        self.info: dict[str, dict] = {}        # loginId → empInfoList item
        self.derived_status: dict[str, int] = {}  # loginId → 轉換後 status（見 status.compute_status）
        self.trigger_ts: dict[str, float] = {}  # loginId → 觸發時間 (ms)，收到封包時算好快取
        self.retry_count: dict[str, int] = {}  # 本 dataTime 內失敗重試次數
        self.next_retry_at: dict[str, float] = {}  # 本 dataTime 內下次可重試時間 (ms)
        self.giveup: set[str] = set()          # 本 dataTime 內已達重試上限、放棄的 loginId
        self.jumping = False                   # 防止 tick 重入
        self.startup_ids: set[str] = set()     # 啟動當下已就緒，需立即刷門、略過觸發時間判斷
        # 啟動快照可能跨多個封包送達（ws_100002 + ws_100003 常常是同一個 dataTime
        # 分兩則訊息送來），因此用 dataTime 而非「是否為第一個收到的封包」判斷是否
        # 仍屬於啟動批次，dataTime 真的換下一批才關閉這個窗口。
        self._startup_data_time: Optional[str] = None
        self._startup_window_closed = False

    def on_ws_packet(self, res: dict) -> None:
        ws_code = res.get("wsCode", "")
        if ws_code not in ("ws_100002", "ws_100003"):
            return

        data_list = res.get("data", [])
        if not isinstance(data_list, list):
            data_list = [data_list]

        _data = next(
            (d for d in data_list
             if d.get("regionInfo", {}).get("regionId") == self.region_id),
            None,
        )
        if not _data:
            log.debug(f"regionId={self.region_id} 不在本次封包中")
            return

        # dataTime 更新 → 重置重試狀態，允許同一批人重新嘗試
        if _data.get("dataTime") and _data["dataTime"] != self.data_time:
            is_first_batch = self.data_time is None
            self.data_time = _data["dataTime"]
            self.retry_count = {}
            self.next_retry_at = {}
            self.giveup = set()
            log.info(f"dataTime 更新: {self.data_time}，重試狀態已重置")

            if is_first_batch:
                self._startup_data_time = self.data_time
            else:
                self._startup_window_closed = True

        # 快取 empInfoList（ws_100003 補充人員資料），並預先算好觸發時間、轉換後 status。
        # 注意：empInfoList 最外層的 status 欄位語意跟這裡的 ready_status 不同（對應
        # staffpilot 前端改名存成 statusFuture 的那個欄位），實際要判斷的 status 得靠
        # currentWorkInfo/nextWorkInfo/tableStatus 用 compute_status() 重新算出來。
        for item in _data.get("empInfoList", []):
            login_id = item["loginId"]
            self.info[login_id] = item
            self.derived_status[login_id] = compute_status(item)

            work_time = (item.get("nextWorkInfo") or {}).get("workTime")
            parsed = parse_worktime(work_time)
            if parsed is not None:
                self.trigger_ts[login_id] = parsed - self.trigger_before_work_s * 1000
            else:
                self.trigger_ts.pop(login_id, None)

        # 篩出轉換後 status ∈ ready_status
        ready = [
            item["loginId"]
            for item in _data.get("empInfoList", [])
            if self.derived_status.get(item["loginId"]) in self.ready_status
        ]
        if ready:
            existing = set(self.ready_list)
            new_ids = [lid for lid in ready if lid not in existing]
            self.ready_list.extend(new_ids)
            log.info(f"ready_list 新增: {new_ids}  總計: {self.ready_list}")

            startup_active = (
                not self._startup_window_closed
                and self.data_time == self._startup_data_time
            )
            if startup_active:
                self.startup_ids.update(new_ids)
                log.info(f"啟動時已就緒，將立即刷門（略過觸發時間）: {new_ids}")

    async def tick(self) -> None:
        """每個 tick_interval 執行一次，判斷是否需要打 idCheck。"""
        if self.jumping:
            return
        if not self.data_time or not self.ready_list:
            return

        now = now_ms()
        pending = [
            lid for lid in self.ready_list
            if lid not in self.desk
            and lid not in self.giveup
            and now >= self.next_retry_at.get(lid, 0)
        ]
        if not pending:
            return

        self.jumping = True
        try:
            tasks = []
            for login_id in pending:
                if login_id in self.startup_ids:
                    log.info(f"啟動立即刷門，略過觸發時間判斷: {login_id}")
                else:
                    trigger_ts = self.trigger_ts.get(login_id)
                    if trigger_ts is None or now <= trigger_ts:
                        continue

                tasks.append(self._do_id_check(login_id))

            if tasks:
                await asyncio.gather(*tasks)
        finally:
            self.jumping = False

    async def _do_id_check(self, login_id: str) -> None:
        loop = asyncio.get_event_loop()
        log.info(f"▶ 發起 idCheck: {login_id}")
        try:
            result = await loop.run_in_executor(None, self.id_check_client.check, login_id)
            self.desk[login_id] = self.data_time
            self.retry_count.pop(login_id, None)
            self.next_retry_at.pop(login_id, None)
            self.startup_ids.discard(login_id)
            log.info(f"✓ idCheck 成功: {login_id}  target={result.get('target')}")
            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor",
                f"✓ 刷門成功: {login_id}",
                {"loginId": login_id, "target": result.get("target"), "dataTime": self.data_time, **result},
            )
        except Exception as err:
            count = self.retry_count.get(login_id, 0) + 1
            self.retry_count[login_id] = count
            if count >= self.max_id_check_retry:
                self.giveup.add(login_id)
                log.error(f"✗✗ idCheck 已達重試上限({self.max_id_check_retry})，放棄: {login_id}  err={err}")
                anal = f"✗✗ 刷門失敗，已放棄重試: {login_id}"
            else:
                self.next_retry_at[login_id] = now_ms() + self.retry_backoff_s * 1000
                log.warning(
                    f"✗ idCheck 失敗（第 {count}/{self.max_id_check_retry} 次），"
                    f"{self.retry_backoff_s}s 後重試: {login_id}  err={err}"
                )
                anal = f"✗ 刷門失敗（第 {count} 次）: {login_id}"
            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor",
                anal,
                {"loginId": login_id, "error": str(err), "retryCount": count, "dataTime": self.data_time},
            )

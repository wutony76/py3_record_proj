"""
荷官（dealer）三段式流程狀態機：
  1. 進門：上崗前 trigger_before_work_s 秒，呼叫 idCheck
  2. 確認進門：上崗時間到了之後，再呼叫一次 idCheck 確認
  3. 打卡：確認進門成功後，等到上崗時間 ±duty_window_s 秒內呼叫 onDutyConfirm

腳本啟動時，第一批封包（用 dataTime 判斷，跨 ws_100001 多則訊息也算同一批）中
已就緒的荷官，略過進門觸發時間判斷，且進門成功後跳過「確認進門」直接上桌
（只做 進門＋上桌 兩步），追趕開機前就已符合條件、可能已經錯過正常觸發窗口的人。

跟原始 staffpilot useAutoFlowHandover.js 的一個刻意簡化：原版用 `_idCheckedOnce` +
dataTime 封包重置 + 額外的 `_overdueLockedWorkTime` map 三者搭配，判斷「這個人這班次
是否已處理過」。這裡改成直接拿 nextWorkInfo.workTime 本身當作班次的識別鍵
（done_for_work_time），只要 workTime 沒變就不重打，一旦排到新班次（workTime 改變）
自然就會再次符合觸發條件，不需要額外的封包重置或例外 map，行為等價但更不容易漏處理
邊界情況。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .dealer_status import compute_dealer_status
from .dev_log import DevLogger
from .duty_client import DutyClient
from .id_check_client import IdCheckClient
from .logging_setup import log
from .time_utils import now_ms, parse_worktime


class DealerFlowState:
    def __init__(
        self,
        region_id: int,
        id_check_client: IdCheckClient,
        duty_client: DutyClient,
        dev_logger: DevLogger,
        ready_status: frozenset = frozenset({1, 11}),
        trigger_before_work_s: int = 3 * 60,
        overdue_after_work_s: int = 5 * 60,
        duty_window_s: int = 60,
        max_id_check_retry: int = 3,
        retry_backoff_s: int = 10,
    ):
        self.region_id = region_id
        self.id_check_client = id_check_client
        self.duty_client = duty_client
        self.dev_logger = dev_logger
        self.ready_status = ready_status
        self.trigger_before_work_s = trigger_before_work_s
        self.overdue_after_work_s = overdue_after_work_s
        self.duty_window_s = duty_window_s
        self.max_id_check_retry = max_id_check_retry
        self.retry_backoff_s = retry_backoff_s

        self.data_time: Optional[str] = None
        self.ready_list: list[str] = []
        self.info: dict[str, dict] = {}
        self.derived_status: dict[str, int] = {}
        self.work_time_raw: dict[str, str] = {}       # loginId → 原始 nextWorkInfo.workTime 字串
        self.trigger_ts: dict[str, float] = {}         # loginId → 進門觸發時間 (ms)

        # 步驟 1：進門
        self.retry_count: dict[str, int] = {}
        self.next_retry_at: dict[str, float] = {}

        # 步驟 2：確認進門（進門成功後，等上崗時間到再打一次 idCheck）
        self.awaiting_confirm: dict[str, str] = {}     # loginId → workTime
        self.confirm_retry_count: dict[str, int] = {}
        self.confirm_next_retry_at: dict[str, float] = {}

        # 步驟 3：打卡
        self.desk: dict[str, str] = {}                 # loginId → workTime，等待打卡

        self.done_for_work_time: dict[str, str] = {}   # loginId → 已處理完（成功/放棄）的 workTime
        self.jumping = False

        # 啟動追趕：第一批封包已就緒的人，進門略過觸發時間、成功後跳過確認直接上桌
        self.startup_ids: set[str] = set()
        self._startup_data_time: Optional[str] = None
        self._startup_window_closed = False

    def on_ws_packet(self, res: dict) -> None:
        if res.get("wsCode") != "ws_100001":
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
            return

        if _data.get("dataTime") and _data["dataTime"] != self.data_time:
            is_first_batch = self.data_time is None
            self.data_time = _data["dataTime"]
            if is_first_batch:
                self._startup_data_time = self.data_time
            else:
                self._startup_window_closed = True

        for item in _data.get("empInfoList", []):
            login_id = item["loginId"]
            self.info[login_id] = item
            self.derived_status[login_id] = compute_dealer_status(item)

            work_time = (item.get("nextWorkInfo") or {}).get("workTime")

            old_work_time = self.work_time_raw.get(login_id)
            if (
                work_time and old_work_time and work_time != old_work_time
                and login_id in self.ready_list
                and login_id not in self.awaiting_confirm
                and login_id not in self.desk
                and self.done_for_work_time.get(login_id) != old_work_time
            ):
                log.warning(
                    f"[dealer] ⚠ {login_id} 尚未進門，workTime 已從 {old_work_time} 變成 {work_time}，"
                    "舊班次可能被錯過"
                )

            if work_time:
                self.work_time_raw[login_id] = work_time
                parsed = parse_worktime(work_time)
                self.trigger_ts[login_id] = (
                    parsed - self.trigger_before_work_s * 1000 if parsed is not None else None
                )
            else:
                self.work_time_raw.pop(login_id, None)
                self.trigger_ts.pop(login_id, None)

        ready = [
            item["loginId"]
            for item in _data.get("empInfoList", [])
            if self.derived_status.get(item["loginId"]) in self.ready_status
        ]
        if ready:
            existing = set(self.ready_list)
            new_ids = [lid for lid in ready if lid not in existing]
            self.ready_list.extend(new_ids)
            if new_ids:
                log.info(f"[dealer] ready_list 新增: {new_ids}  總計: {self.ready_list}")

                startup_active = (
                    not self._startup_window_closed
                    and self.data_time == self._startup_data_time
                )
                if startup_active:
                    self.startup_ids.update(new_ids)
                    log.info(f"[dealer] 啟動時已就緒，將立即進門+上桌（略過確認進門）: {new_ids}")

    async def tick(self) -> None:
        if self.jumping:
            return
        self.jumping = True
        try:
            await self._tick_id_check()
            await self._tick_confirm_check()
            await self._tick_duty_confirm()
        finally:
            self.jumping = False

    # ── 步驟 1：進門 ──────────────────────────────────────
    async def _tick_id_check(self) -> None:
        now = now_ms()
        pending = [
            lid for lid in self.ready_list
            if lid not in self.awaiting_confirm
            and lid not in self.desk
            and self.work_time_raw.get(lid) != self.done_for_work_time.get(lid)
            and now >= self.next_retry_at.get(lid, 0)
        ]
        if not pending:
            return

        tasks = []
        for login_id in pending:
            if login_id in self.startup_ids:
                log.info(f"[dealer] 啟動立即進門，略過觸發時間判斷: {login_id}")
            else:
                trigger_ts = self.trigger_ts.get(login_id)
                if trigger_ts is None or now <= trigger_ts:
                    continue
            tasks.append(self._do_id_check(login_id))

        if tasks:
            await asyncio.gather(*tasks)

    async def _do_id_check(self, login_id: str) -> None:
        loop = asyncio.get_event_loop()
        work_time = self.work_time_raw.get(login_id)
        is_startup = login_id in self.startup_ids
        log.info(f"[dealer] ▶ 發起 idCheck（進門）: {login_id}")
        try:
            result = await loop.run_in_executor(None, self.id_check_client.check, login_id)
            self.retry_count.pop(login_id, None)
            self.next_retry_at.pop(login_id, None)
            self.startup_ids.discard(login_id)

            if is_startup:
                log.info(
                    f"[dealer] ✓ 進門成功（啟動追趕）: {login_id}  target={result.get('target')}，"
                    "略過確認進門，直接上桌"
                )
                await loop.run_in_executor(
                    None,
                    self.dev_logger.log,
                    "py3-monitor-dealer",
                    f"✓ 進門成功（啟動追趕）: {login_id}",
                    {"loginId": login_id, "target": result.get("target"), "workTime": work_time, **result},
                )
                await self._do_duty_confirm(login_id, work_time)
                return

            work_ts = parse_worktime(work_time)
            if work_ts is not None and now_ms() - work_ts > self.overdue_after_work_s * 1000:
                log.warning(f"[dealer] ✓ 進門成功但已逾時，不再確認進門: {login_id}")
                self.done_for_work_time[login_id] = work_time
            else:
                self.awaiting_confirm[login_id] = work_time
                log.info(f"[dealer] ✓ 進門成功: {login_id}  target={result.get('target')}，等上崗時間到再確認")

            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor-dealer",
                f"✓ 進門成功: {login_id}",
                {"loginId": login_id, "target": result.get("target"), "workTime": work_time, **result},
            )
        except Exception as err:
            count = self.retry_count.get(login_id, 0) + 1
            self.retry_count[login_id] = count
            if count >= self.max_id_check_retry:
                self.done_for_work_time[login_id] = work_time
                self.startup_ids.discard(login_id)
                log.error(f"[dealer] ✗✗ 進門已達重試上限({self.max_id_check_retry})，放棄: {login_id}  err={err}")
                anal = f"✗✗ 進門失敗，已放棄重試: {login_id}"
            else:
                self.next_retry_at[login_id] = now_ms() + self.retry_backoff_s * 1000
                log.warning(
                    f"[dealer] ✗ 進門失敗（第 {count}/{self.max_id_check_retry} 次），"
                    f"{self.retry_backoff_s}s 後重試: {login_id}  err={err}"
                )
                anal = f"✗ 進門失敗（第 {count} 次）: {login_id}"
            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor-dealer",
                anal,
                {"loginId": login_id, "error": str(err), "retryCount": count, "workTime": work_time},
            )

    # ── 步驟 2：確認進門（上崗時間到了之後再打一次 idCheck）──
    async def _tick_confirm_check(self) -> None:
        now = now_ms()
        pending = [
            lid for lid, work_time in self.awaiting_confirm.items()
            if now >= self.confirm_next_retry_at.get(lid, 0)
        ]
        if not pending:
            return

        tasks = []
        for login_id in pending:
            work_ts = parse_worktime(self.awaiting_confirm[login_id])
            if work_ts is None or now < work_ts:
                continue  # 上崗時間還沒到，先不確認
            tasks.append(self._do_confirm_check(login_id))

        if tasks:
            await asyncio.gather(*tasks)

    async def _do_confirm_check(self, login_id: str) -> None:
        loop = asyncio.get_event_loop()
        work_time = self.awaiting_confirm[login_id]
        log.info(f"[dealer] ▶ 發起 idCheck（確認進門）: {login_id}")
        try:
            result = await loop.run_in_executor(None, self.id_check_client.check, login_id)
            del self.awaiting_confirm[login_id]
            self.confirm_retry_count.pop(login_id, None)
            self.confirm_next_retry_at.pop(login_id, None)
            self.desk[login_id] = work_time
            log.info(f"[dealer] ✓ 確認進門成功: {login_id}  target={result.get('target')}，等待打卡")
            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor-dealer",
                f"✓ 確認進門成功: {login_id}",
                {"loginId": login_id, "target": result.get("target"), "workTime": work_time, **result},
            )
        except Exception as err:
            count = self.confirm_retry_count.get(login_id, 0) + 1
            self.confirm_retry_count[login_id] = count
            if count >= self.max_id_check_retry:
                del self.awaiting_confirm[login_id]
                self.confirm_retry_count.pop(login_id, None)
                self.confirm_next_retry_at.pop(login_id, None)
                self.done_for_work_time[login_id] = work_time
                log.error(f"[dealer] ✗✗ 確認進門已達重試上限({self.max_id_check_retry})，放棄打卡: {login_id}  err={err}")
                anal = f"✗✗ 確認進門失敗，放棄打卡: {login_id}"
            else:
                self.confirm_next_retry_at[login_id] = now_ms() + self.retry_backoff_s * 1000
                log.warning(
                    f"[dealer] ✗ 確認進門失敗（第 {count}/{self.max_id_check_retry} 次），"
                    f"{self.retry_backoff_s}s 後重試: {login_id}  err={err}"
                )
                anal = f"✗ 確認進門失敗（第 {count} 次）: {login_id}"
            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor-dealer",
                anal,
                {"loginId": login_id, "error": str(err), "retryCount": count, "workTime": work_time},
            )

    # ── 步驟 3：打卡 ──────────────────────────────────────
    async def _tick_duty_confirm(self) -> None:
        now = now_ms()
        tasks = []
        for login_id, work_time in list(self.desk.items()):
            work_ts = parse_worktime(work_time)
            if work_ts is None:
                del self.desk[login_id]
                continue

            delta = work_ts - now
            if delta > 0:
                continue  # 理論上不會發生（確認進門本身就要求上崗時間已到），保守起見仍檢查

            if abs(delta) <= self.duty_window_s * 1000:
                tasks.append(self._do_duty_confirm(login_id, work_time))
            else:
                log.warning(f"[dealer] ✗ 錯過打卡視窗（逾 {self.duty_window_s}s），放棄: {login_id}")
                del self.desk[login_id]
                self.done_for_work_time[login_id] = work_time

        if tasks:
            await asyncio.gather(*tasks)

    async def _do_duty_confirm(self, login_id: str, work_time: str) -> None:
        loop = asyncio.get_event_loop()
        log.info(f"[dealer] ▶ 發起 onDutyConfirm（打卡）: {login_id}")
        try:
            result = await loop.run_in_executor(None, self.duty_client.confirm, login_id)
            log.info(f"[dealer] ✓ 打卡成功: {login_id}")
            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor-dealer",
                f"✓ 打卡成功: {login_id}",
                {"loginId": login_id, "workTime": work_time, **result},
            )
        except Exception as err:
            log.warning(f"[dealer] ✗ 打卡失敗（本班不再重試）: {login_id}  err={err}")
            await loop.run_in_executor(
                None,
                self.dev_logger.log,
                "py3-monitor-dealer",
                f"✗ 打卡失敗: {login_id}",
                {"loginId": login_id, "workTime": work_time, "error": str(err)},
            )
        finally:
            # 不管成功失敗，這一班的流程都結束了；下一班（workTime 改變）才會再次觸發。
            # 用 pop 而非 del：啟動追趕路徑會直接呼叫這裡，desk 裡本來就沒有這筆。
            self.desk.pop(login_id, None)
            self.done_for_work_time[login_id] = work_time

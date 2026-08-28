"""
將 empInfoList 的原始欄位換算成判斷用的 status。

WS 封包最外層的 `status` 欄位語意跟這裡算出來的不同（staffpilot 前端把它改名存成
`statusFuture`，不會拿來跟 1/11 比對）。真正決定「是否即將上崗」的 status，是
staffpilot useMonitorBoardV2.js 的 handle.toCard() / handle.statusCurrent() 用
currentWorkInfo.status、nextWorkInfo.status、tableStatus、temporaryReliefFlag
這幾個原始欄位重新算出來的。此檔案是該邏輯的對應移植，修改雙方任一邊時務必同步。

currentWorkInfo/nextWorkInfo 後端有時會用空字串代替物件（沒有排班時）；JS 對
falsy 值的判斷、對非物件取屬性都不會出錯，這裡改用 js_compat 的 truthy/safe_get
複刻同樣的容錯行為，避免 Python 的 dict.get() 對字串直接丟例外。
"""

from __future__ import annotations

from typing import Optional

from .js_compat import js_truthy, safe_get
from .time_utils import now_ms, parse_worktime

STATUS_REST = 0                        # 休息
STATUS_ABOUT_TO_WORK = 1               # 即將上崗
STATUS_WORKING = 2                     # 已上崗中
STATUS_TEMP_RELIEF_NOT_ENTERED = 11    # 臨時代理、尚未進場
STATUS_EXPIRED = 99                    # 已逾 nextWorkInfo.workTime，卡片失效


def _status_current(item: dict) -> int:
    current_work = item.get("currentWorkInfo")
    next_work = item.get("nextWorkInfo")

    if not js_truthy(current_work) and not js_truthy(next_work):
        return STATUS_REST

    if js_truthy(current_work):
        cur = safe_get(current_work, "status")
        nxt = safe_get(next_work, "status") if js_truthy(next_work) else None

        if nxt == 0:  # 下一段為休息
            if cur == 0:
                return STATUS_REST
            if cur == 1:
                return STATUS_WORKING
            return STATUS_REST
        elif nxt == 1:  # 下一段為工作
            if cur == 0:
                return STATUS_ABOUT_TO_WORK
            if cur == 1:
                return STATUS_WORKING
        elif nxt == 2:  # 途中請假
            if cur == 0:
                return STATUS_REST
            if cur == 1:
                return STATUS_WORKING
            return STATUS_REST
        elif nxt == 3:
            if cur == 0:
                return STATUS_REST
            if cur == 1:
                return STATUS_WORKING
            return STATUS_REST
        return STATUS_REST

    # currentWorkInfo 不存在：第一次交接班資料
    nxt = safe_get(next_work, "status")
    if nxt == 0:
        return STATUS_REST
    if nxt == 1:
        return STATUS_ABOUT_TO_WORK
    return STATUS_REST


def compute_status(item: dict, now: Optional[float] = None) -> int:
    """對應 handle.toCard()：先算 statusCurrent，再套臨時代理／逾期覆寫。"""
    status = _status_current(item)

    current_work = item.get("currentWorkInfo")
    if safe_get(current_work, "temporaryReliefFlag"):
        table_status = item.get("tableStatus")
        if table_status == 0:
            status = STATUS_TEMP_RELIEF_NOT_ENTERED
        elif table_status == 1:
            status = STATUS_WORKING

    next_work_time = safe_get(item.get("nextWorkInfo"), "workTime")
    if next_work_time:
        raw_ts = parse_worktime(next_work_time)
        if raw_ts is not None and (now_ms() if now is None else now) > raw_ts:
            status = STATUS_EXPIRED

    return status

"""
荷官（dealer）專用的 status 換算，移植自 staffpilot useShiftBoardV2.js 的
handle.statusCurrent()。跟 status.py（監台版）分支結果不一樣，不能共用：
同樣是 cur=1,next=0 或 cur=1,next=1，監台判 2（已上崗中），荷官判 11；
另外還多一個 tableStatus===1 直接短路判 2 的規則，監台沒有這條。
"""

from __future__ import annotations

from typing import Optional

from .time_utils import now_ms, parse_worktime

STATUS_REST = 0
STATUS_ABOUT_TO_WORK = 1
STATUS_WORKING = 2
STATUS_ELEVEN = 11  # 荷官這裡的 11 是 statusCurrent 自己算出來的分支，不是臨時代理覆寫
STATUS_EXPIRED = 99


def compute_dealer_status(item: dict, now: Optional[float] = None) -> int:
    if item.get("tableStatus") == 1:
        status = STATUS_WORKING  # 馬上上桌
    else:
        status = _status_current(item)

    next_work_time = (item.get("nextWorkInfo") or {}).get("workTime")
    if next_work_time:
        raw_ts = parse_worktime(next_work_time)
        if raw_ts is not None and (now_ms() if now is None else now) > raw_ts:
            status = STATUS_EXPIRED

    return status


def _status_current(item: dict) -> int:
    current_work = item.get("currentWorkInfo")
    next_work = item.get("nextWorkInfo")

    if current_work is None and next_work is None:
        return STATUS_REST

    if current_work is not None:
        cur = current_work.get("status")
        nxt = next_work.get("status") if next_work is not None else None

        if nxt == 0:  # 下一段為休息
            if cur == 0:
                return STATUS_REST
            if cur == 1:
                return STATUS_ELEVEN
            return STATUS_REST
        elif nxt == 1:  # 下一段為工作
            if cur == 0:
                return STATUS_ABOUT_TO_WORK
            if cur == 1:
                return STATUS_ELEVEN
            if cur == 3:
                return STATUS_ABOUT_TO_WORK
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
    nxt = next_work.get("status")
    if nxt == 0:
        return STATUS_REST
    if nxt == 1:
        return STATUS_ABOUT_TO_WORK
    return STATUS_REST

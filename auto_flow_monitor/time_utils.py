"""workTime 字串解析與時間工具。"""

import time
from datetime import datetime
from typing import Optional

_WORKTIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


def parse_worktime(work_time: Optional[str]) -> Optional[float]:
    """把後端 workTime 字串解析成 Unix timestamp (ms)。"""
    if not work_time:
        return None
    for fmt in _WORKTIME_FORMATS:
        try:
            return datetime.strptime(work_time.split(".")[0], fmt).timestamp() * 1000
        except ValueError:
            continue
    return None


def now_ms() -> float:
    return time.time() * 1000

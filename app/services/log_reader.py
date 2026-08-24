import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import LOG_DIR

_LINE_RE = re.compile(
    r"^\[(?P<time>\d{2}:\d{2}:\d{2})\]\s+"
    r"(?P<rest>.+)$"
)
_DATA_RE = re.compile(r"\[data:\s*(?P<json>\{.*?\})\]")
_SCREENSHOTS_RE = re.compile(r"\[screenshots:\s*(?P<files>[^\]]+)\]")
_SCREENSHOTS_READY_RE = re.compile(r"\[screenshots ready:\s*(?P<files>[^\]]+)\]")


def _parse_line(raw: str) -> Optional[Dict[str, Any]]:
    m = _LINE_RE.match(raw.strip())
    if not m:
        return None

    time_str = m.group("time")
    rest = m.group("rest")

    # 截圖 ready 補行（不是主要 log 條目）
    ready_m = _SCREENSHOTS_READY_RE.search(rest)
    if ready_m and rest.strip().startswith("[screenshots ready"):
        return {
            "time": time_str,
            "type": "screenshots_ready",
            "screenshots_ready": [f.strip() for f in ready_m.group("files").split(",")],
        }

    data_val: Optional[Dict] = None
    data_m = _DATA_RE.search(rest)
    if data_m:
        try:
            data_val = json.loads(data_m.group("json"))
        except json.JSONDecodeError:
            pass
        rest = _DATA_RE.sub("", rest)

    screenshots: List[str] = []
    ss_m = _SCREENSHOTS_RE.search(rest)
    if ss_m:
        screenshots = [f.strip() for f in ss_m.group("files").split(",")]
        rest = _SCREENSHOTS_RE.sub("", rest)

    message = rest.strip()

    return {
        "time": time_str,
        "type": "log",
        "message": message,
        "data": data_val,
        "screenshots": screenshots,
    }


def read_logs(date_str: str) -> List[Dict[str, Any]]:
    """讀取指定日期所有 bucket，回傳解析後的 log 條目列表。"""
    day_dir = LOG_DIR / date_str
    if not day_dir.exists():
        return []

    entries: List[Dict[str, Any]] = []
    for txt_file in sorted(day_dir.glob("*.txt")):
        bucket = txt_file.stem
        raw_lines = txt_file.read_text(encoding="utf-8").splitlines()

        # 把 screenshots_ready 合併到對應的 log 條目
        bucket_entries: List[Dict[str, Any]] = []
        for line in raw_lines:
            parsed = _parse_line(line)
            if parsed is None:
                continue
            if parsed["type"] == "screenshots_ready":
                # 往前找同時間的 log 條目合併
                for entry in reversed(bucket_entries):
                    if entry["time"] == parsed["time"]:
                        entry["screenshots"] = parsed["screenshots_ready"]
                        break
            else:
                parsed["bucket"] = bucket
                bucket_entries.append(parsed)

        entries.extend(bucket_entries)

    return entries


def list_dates() -> List[str]:
    """回傳有資料的日期列表（降冪）。"""
    if not LOG_DIR.exists():
        return []
    return sorted(
        [d.name for d in LOG_DIR.iterdir() if d.is_dir()],
        reverse=True,
    )

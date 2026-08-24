import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import LOG_DIR
from ..core.time_bucket import bucket_day_dir, bucket_filename

_locks: dict[Path, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def _lock_for(path: Path) -> asyncio.Lock:
    async with _locks_guard:
        if path not in _locks:
            _locks[path] = asyncio.Lock()
        return _locks[path]


async def write_log(
    ts: datetime,
    message: str,
    screenshot_files: Optional[List[str]],
    data: Optional[Dict[str, Any]] = None,
) -> Path:
    day_dir = LOG_DIR / bucket_day_dir(ts)
    day_dir.mkdir(parents=True, exist_ok=True)
    file_path = day_dir / bucket_filename(ts)

    line = f"[{ts:%H:%M:%S}] {message}"
    if data:
        line += f" [data: {json.dumps(data, ensure_ascii=False)}]"
    if screenshot_files:
        files_str = ", ".join(screenshot_files)
        line += f" [screenshots: {files_str}]"
    line += "\n"

    lock = await _lock_for(file_path)
    async with lock:
        with file_path.open("a", encoding="utf-8") as f:
            f.write(line)

    return file_path

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from playwright.async_api import Browser, async_playwright

from ..core.config import SCREENSHOT_DIR
from ..core.time_bucket import bucket_day_dir, bucket_filename

WAIT_AFTER_LOAD_S = 20

_playwright = None
_browser: Optional[Browser] = None
# 同一時間最多 1 個截圖任務，避免大量並發壓垮 browser
_semaphore: Optional[asyncio.Semaphore] = None


async def start_browser() -> None:
    global _playwright, _browser, _semaphore
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)
    _semaphore = asyncio.Semaphore(2)


async def stop_browser() -> None:
    global _playwright, _browser
    if _browser is not None:
        await _browser.close()
    if _playwright is not None:
        await _playwright.stop()


async def _capture_one(ts: datetime, url: str, index: int) -> Path:
    """載入單一 URL，等待 WAIT_AFTER_LOAD_S 秒後截圖。"""
    if _browser is None:
        raise RuntimeError("Browser is not started")

    day_dir = SCREENSHOT_DIR / bucket_day_dir(ts)
    day_dir.mkdir(parents=True, exist_ok=True)
    bucket = bucket_filename(ts).removesuffix(".txt")
    file_path = day_dir / f"{bucket}_{ts:%H%M%S}_{index}.png"

    page = await _browser.new_page()
    try:
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(WAIT_AFTER_LOAD_S)
        await page.screenshot(path=str(file_path), full_page=True)
    finally:
        await page.close()

    return file_path


async def capture_and_append_log(ts: datetime, urls: List[str], log_path: Path) -> None:
    """背景任務：對多個 URL 依序截圖，完成後將截圖檔名 append 到 log 檔。
    使用 semaphore 確保同一時間只有一個任務在跑，避免並發壓垮 browser。
    """
    from ..services.log_writer import append_screenshot_log

    sem = _semaphore
    if sem is None:
        return

    async with sem:
        results: List[Path] = []
        for i, url in enumerate(urls):
            try:
                path = await _capture_one(ts, url, i)
                results.append(path)
            except Exception:
                pass  # 單一 URL 失敗不中斷整批

        if results:
            filenames = [p.name for p in results]
            await append_screenshot_log(ts, log_path, filenames)

from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, async_playwright

from ..core.config import SCREENSHOT_DIR
from ..core.time_bucket import bucket_day_dir, bucket_filename

_playwright = None
_browser: Optional[Browser] = None


async def start_browser() -> None:
    global _playwright, _browser
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)


async def stop_browser() -> None:
    global _playwright, _browser
    if _browser is not None:
        await _browser.close()
    if _playwright is not None:
        await _playwright.stop()


async def capture(ts: datetime, url: str) -> Path:
    if _browser is None:
        raise RuntimeError("Browser is not started")

    day_dir = SCREENSHOT_DIR / bucket_day_dir(ts)
    day_dir.mkdir(parents=True, exist_ok=True)
    bucket = bucket_filename(ts).removesuffix(".txt")
    file_path = day_dir / f"{bucket}_{ts:%H%M%S}.png"

    page = await _browser.new_page()
    try:
        await page.goto(url, wait_until="networkidle")
        await page.screenshot(path=str(file_path), full_page=True)
    finally:
        await page.close()

    return file_path

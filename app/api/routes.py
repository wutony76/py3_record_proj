from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..models.schemas import LogRequest, LogResponse
from ..services import log_writer, screenshot

router = APIRouter()


@router.post("/log", response_model=LogResponse)
async def create_log(payload: LogRequest) -> LogResponse:
    ts = payload.timestamp or datetime.now()

    screenshot_filename = None
    if payload.screenshot:
        if not payload.url:
            raise HTTPException(status_code=400, detail="url is required when screenshot=true")
        screenshot_path = await screenshot.capture(ts, payload.url)
        screenshot_filename = screenshot_path.name

    log_path = await log_writer.write_log(ts, payload.message, screenshot_filename)

    return LogResponse(
        status="ok",
        log_file=log_path.name,
        screenshot_file=screenshot_filename,
    )

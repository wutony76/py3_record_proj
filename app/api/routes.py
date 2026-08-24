from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..models.schemas import LogRequest, LogResponse
from ..services import log_reader, log_writer, screenshot

router = APIRouter()


@router.get("/logs/dates")
async def get_dates() -> List[str]:
    return log_reader.list_dates()


@router.get("/logs/{date}")
async def get_logs(date: str) -> Dict[str, Any]:
    entries = log_reader.read_logs(date)
    return {"date": date, "entries": entries}


@router.post("/log", response_model=LogResponse)
async def create_log(payload: LogRequest, background_tasks: BackgroundTasks) -> LogResponse:
    ts = payload.timestamp or datetime.now()

    if payload.screenshot and not payload.url:
        raise HTTPException(status_code=400, detail="url is required when screenshot=true")

    log_path = await log_writer.write_log(ts, payload.message, None, payload.data)

    if payload.screenshot:
        background_tasks.add_task(screenshot.capture_and_append_log, ts, payload.url, log_path)

    return LogResponse(
        status="ok",
        log_file=log_path.name,
        screenshot_files=None,
    )

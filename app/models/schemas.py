from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class LogRequest(BaseModel):
    message: str
    timestamp: Optional[datetime] = None
    screenshot: bool = False
    url: Optional[List[str]] = None
    data: Optional[Dict[str, Any]] = None


class LogResponse(BaseModel):
    status: str
    log_file: str
    screenshot_files: Optional[List[str]] = None

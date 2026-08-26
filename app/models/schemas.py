from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, field_validator


class LogRequest(BaseModel):
    message: Optional[str] = None
    anal: Optional[str] = None
    tag: Optional[str] = None
    timestamp: Optional[datetime] = None
    screenshot: bool = False
    url: Optional[List[str]] = None
    data: Optional[Dict[str, Any]] = None

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("anal", mode="before")
    @classmethod
    def normalize_anal(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            return v
        # 非字串（如 list、dict）轉為 JSON 字串
        import json
        return json.dumps(v, ensure_ascii=False)


class LogResponse(BaseModel):
    status: str
    log_file: str
    screenshot_files: Optional[List[str]] = None

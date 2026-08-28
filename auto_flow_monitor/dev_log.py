"""本地紀錄回報（py3_record_proj /api/log），失敗靜默。"""

import requests


class DevLogger:
    def __init__(self, url: str, timeout: float = 3):
        self.url = url
        self.timeout = timeout

    def log(self, tag: str, anal: str, data: dict) -> None:
        try:
            requests.post(
                self.url,
                json={
                    "tag": tag,
                    "anal": anal,
                    "data": data,
                    "screenshot": False,
                },
                timeout=self.timeout,
            )
        except Exception:
            pass

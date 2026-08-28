"""封裝 onDutyConfirm（打卡/上桌）API：跟 idCheck 不同，這支需要登入 token。"""

import requests

from .signing import make_req_id, sign_duty_confirm
from .time_utils import now_ms

_SUCCESS_CODES = {0, 200, 201}
_TERMINAL_WEB = 1


class DutyClient:
    def __init__(
        self,
        api_base: str,
        secret: str,
        cmd: str,
        token: str,
        timeout: float = 10,
    ):
        self.api_base = api_base
        self.secret = secret
        self.cmd = cmd
        self.token = token
        self.timeout = timeout

    def confirm(self, login_id: str) -> dict:
        """同步呼叫，設計上供 run_in_executor 放到背景執行緒使用。"""
        ts = str(int(now_ms()))
        req_id = make_req_id()
        payload = {
            "version": "1.0",
            "reqId": req_id,
            "identity": req_id,
            "token": self.token,
            "cmd": self.cmd,
            "terminal": _TERMINAL_WEB,
            "loginId": login_id,
            "useSign": True,
            "sign": sign_duty_confirm(ts, self.cmd, login_id, self.secret),
            "ts": ts,
        }
        url = f"{self.api_base}/{self.cmd}"
        resp = requests.post(
            url,
            json=payload,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"},
            verify=False,
        )
        resp.raise_for_status()
        envelope = resp.json()
        code = envelope.get("code")
        if code not in _SUCCESS_CODES:
            raise RuntimeError(f"onDutyConfirm 失敗: code={code} msg={envelope.get('message', '')}")
        return envelope.get("data") or {}

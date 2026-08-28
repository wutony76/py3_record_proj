"""封裝 idCheck API：組 payload、簽名、送出、判斷成功/失敗。"""

import urllib3
import requests

from .dev_log import DevLogger
from .signing import make_req_id, sign_id_check
from .time_utils import now_ms

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class IdCheckClient:
    def __init__(
        self,
        api_base: str,
        secret: str,
        cmd: str,
        dev_logger: DevLogger,
        timeout: float = 20,
    ):
        self.api_base = api_base
        self.secret = secret
        self.cmd = cmd
        self.dev_logger = dev_logger
        self.timeout = timeout

    def check(self, login_id: str) -> dict:
        """同步呼叫，設計上供 run_in_executor 放到背景執行緒使用。"""
        ts = str(int(now_ms()))
        req_id = make_req_id()
        payload = {
            "channel": "bg",
            "clientType": 1,
            "reqId": req_id,
            "identity": req_id,
            "version": "1.0",
            "cmd": self.cmd,
            "loginId": login_id,
            "sign": sign_id_check(login_id, ts, self.secret, self.cmd),
            "ts": ts,
        }
        url = f"{self.api_base}/{self.cmd}"
        self.dev_logger.log(
            tag="py3-monitor",
            anal=f"發起 idCheck: {login_id}",
            data={"loginId": login_id, "ts": ts, "reqId": req_id},
        )
        print(f"[idCheck] → POST {url}")
        print(f"  loginId  : {login_id}")

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
        msg = envelope.get("message", "")
        data = envelope.get("data") or {}
        if not envelope or code != 0:
            self.dev_logger.log(
                tag="py3-monitor",
                anal=f"idCheck 失敗: {login_id}",
                data={"loginId": login_id, "code": code, "message": msg},
            )
            raise RuntimeError(f"idCheck 失敗: code={code} msg={msg}")
        return data

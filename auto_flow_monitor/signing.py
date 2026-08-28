"""idCheck / onDutyConfirm 請求所需的簽名與識別碼產生。"""

import hashlib
import uuid


def make_req_id() -> str:
    return uuid.uuid4().hex


def sign_id_check(login_id: str, ts: str, secret: str, cmd: str) -> str:
    raw = f"{login_id}{ts}{secret}{cmd}"
    return hashlib.md5(raw.encode()).hexdigest()


def sign_duty_confirm(ts: str, cmd: str, login_id: str, secret: str) -> str:
    """對應 request.js 的 handle.encryptSignDuty：欄位順序、密鑰都跟 idCheck 不同。"""
    raw = f"{ts}{secret}{cmd}{login_id}"
    return hashlib.md5(raw.encode()).hexdigest()

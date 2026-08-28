"""集中管理所有可調參數，方便日後修改。"""

from __future__ import annotations

from dataclasses import dataclass, field


def _load_ems_token() -> str:
    """從不進 git 的 secrets_local.py 讀 EMS_TOKEN（onDutyConfirm 需要），沒有就回傳空字串。"""
    try:
        from . import secrets_local
        return getattr(secrets_local, "EMS_TOKEN", "")
    except ImportError:
        return ""


@dataclass(frozen=True)
class Settings:
    ws_url: str = "wss://api.js-yichang.com/ems/ws"
    api_base: str = "https://api.js-yichang.com/ems/api"
    dev_log_url: str = "http://127.0.0.1:8000/api/log"   # py3_record_proj 本地紀錄

    id_check_secret: str = "p97*kf&56re#^"
    id_check_cmd: str = "idCheck"
    id_check_timeout_s: float = 20      # idCheck API 逾時秒數
    dev_log_timeout_s: float = 3        # 本地紀錄 API 逾時秒數

    trigger_before_work_s: int = 3 * 60   # 監台上崗前幾秒觸發
    tick_interval_s: float = 0.5           # 每幾秒判斷一次觸發時間
    reconnect_delay_s: int = 5             # 斷線重連等待秒數

    ready_status: frozenset = field(default_factory=lambda: frozenset({1, 11}))  # 監台可觸發的 status 值

    max_id_check_retry: int = 3   # idCheck 失敗最多重試次數（同一 dataTime 內）
    retry_backoff_s: int = 10     # 失敗後重試間隔秒數

    # ── 荷官（dealer）二段式流程：進門 idCheck + 打卡 onDutyConfirm ──
    ems_token: str = field(default_factory=_load_ems_token)   # onDutyConfirm 需要登入 token，見 secrets_local.py
    duty_secret: str = "n63*8f&9jre^#"            # 跟 id_check_secret 不同組密鑰
    duty_cmd: str = "onDutyConfirm"
    duty_timeout_s: float = 10
    dealer_ready_status: frozenset = field(default_factory=lambda: frozenset({1}))
    dealer_trigger_before_work_s: int = 3 * 60    # 荷官上崗前幾秒觸發第一次 idCheck（進門）
    dealer_overdue_after_work_s: int = 5 * 60     # 進門成功時已逾上崗時間超過此秒數，視為過期、不再確認進門
    duty_window_s: int = 60                        # 上崗時間後幾秒內要完成打卡，超過就放棄

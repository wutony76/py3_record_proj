"""集中管理所有可調參數，方便日後修改。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    ws_url: str = "wss://api.js-yichang.com/ems/ws"
    api_base: str = "https://api.js-yichang.com/ems/api"
    dev_log_url: str = "http://127.0.0.1:8000/api/log"   # py3_record_proj 本地紀錄

    id_check_secret: str = "p97*kf&56re#^"
    id_check_cmd: str = "idCheck"
    id_check_timeout_s: float = 20      # idCheck API 逾時秒數
    dev_log_timeout_s: float = 3        # 本地紀錄 API 逾時秒數

    trigger_before_work_s: int = 3 * 60   # 上崗前幾秒觸發
    tick_interval_s: float = 0.5           # 每幾秒判斷一次觸發時間
    reconnect_delay_s: int = 5             # 斷線重連等待秒數

    ready_status: frozenset = field(default_factory=lambda: frozenset({1, 11}))  # 可觸發的 status 值

    max_id_check_retry: int = 3   # idCheck 失敗最多重試次數（同一 dataTime 內）
    retry_backoff_s: int = 10     # 失敗後重試間隔秒數

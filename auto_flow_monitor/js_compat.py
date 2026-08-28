"""
複刻 JS 在這段移植邏輯裡依賴的兩個行為：

1. truthy 判斷：JS 的 `!x` 對 ''（空字串）/0/null/undefined/false 為真（視為
   falsy），但對 {}（空物件）為假（視為 truthy）。Python 的 `bool('')` 也是
   False，但直接用 Python truthy 沒問題的地方，容易在改動時被誤用成
   `is not None`，反而漏接空字串。
2. 安全取值：JS 對非物件（例如字串）取屬性（`''.status`）不會報錯，靜默回傳
   undefined；後端有時候會用 "" 代替物件（例如沒有排班時 nextWorkInfo 送 ""），
   Python 的 dict.get() 對字串呼叫會直接丟 AttributeError，這裡統一擋掉。
"""

from __future__ import annotations

from typing import Any, Optional


def js_truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, (int, float)):
        return value != 0
    return True


def safe_get(value: Any, key: str) -> Optional[Any]:
    return value.get(key) if isinstance(value, dict) else None

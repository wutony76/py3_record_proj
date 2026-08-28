"""
auto_flow_monitor
──────────────────
仿照 staffpilot AutoFlowMonitorView 邏輯的獨立 Python 腳本。

功能：
  1. 連線 EMS WebSocket（ws_100002 監台看板）
  2. 解析 empInfoList，用 status.compute_status() 把 currentWorkInfo/nextWorkInfo/
     tableStatus 轉換成前端語意的 status（移植自 staffpilot handle.toCard()），
     找出轉換後 status ∈ ready_status 的即將上崗人員
  3. 每 tick_interval_s 判斷是否到達觸發時間（nextWorkInfo.workTime - trigger_before_work_s）
  4. 到達時呼叫 idCheck API（MD5 簽名）完成自動刷門
  5. 成功後將該 loginId 記入 desk dict，不再重複打
  6. 腳本啟動時，第一批封包中已是 status ∈ ready_status 的人員立即刷門一次，
     不等待觸發時間（避免啟動前已錯過的觸發窗口）

使用：
  pip install websockets requests
  python -m auto_flow_monitor --region 37
"""

import argparse
import asyncio

from .config import Settings
from .logging_setup import configure_logging
from .monitor import AutoFlowMonitor

log = configure_logging()


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoFlow Monitor")
    parser.add_argument("--region", type=int, default=37, help="regionId（預設 37）")
    args = parser.parse_args()

    log.info(f"AutoFlow Monitor 啟動  regionId={args.region}")
    monitor = AutoFlowMonitor(region_id=args.region, settings=Settings())
    asyncio.run(monitor.run())


if __name__ == "__main__":
    main()

"""
手動測試腳本：需先啟動 server
  python3 -m uvicorn app.main:app --reload
"""

import requests

BASE = "http://127.0.0.1:8000"


def test_log_only():
    print("=== 測試 1：純 log，無截圖 ===")
    resp = requests.post(f"{BASE}/api/log", json={
        "message": "排程執行完成",
    })
    print("status_code:", resp.status_code)
    print("response:   ", resp.json())
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    print("PASS\n")


def test_log_with_screenshot():
    print("=== 測試 2：附截圖 ===")
    resp = requests.post(f"{BASE}/api/log", json={
        "message": "截圖測試",
        "data": {
            "job_id": 123,
            "status": "success",
            "count": 42,
        },
        "screenshot": True,
        "url": ["https://backend.kecoralwell312.com/ems/#/v2/monitorGroup?regionId=37"],
    }, timeout=120)
    print("status_code:", resp.status_code)
    print("response:   ", resp.json())
    assert resp.status_code == 200
    assert resp.json()["screenshot_files"] is not None
    print("PASS\n")


def test_screenshot_missing_url():
    print("=== 測試 3：screenshot=true 但缺 url（應回 400）===")
    resp = requests.post(f"{BASE}/api/log", json={
        "message": "缺 url 測試",
        "screenshot": True,
    })
    print("status_code:", resp.status_code)
    print("response:   ", resp.json())
    assert resp.status_code == 400
    print("PASS\n")


def test_custom_timestamp():
    print("=== 測試 4：帶自訂 timestamp ===")
    resp = requests.post(f"{BASE}/api/log", json={
        "message": "自訂時間測試",
        "timestamp": "2026-08-24T10:25:30",
    })
    print("status_code:", resp.status_code)
    data = resp.json()
    print("response:   ", data)
    assert resp.status_code == 200
    assert "1020-1040" in data["log_file"]
    print("PASS\n")


def test_log_with_data():
    print("=== 測試 5：帶 data 欄位 ===")
    resp = requests.post(f"{BASE}/api/log", json={
        "message": "data 測試",
        "data": {
            "job_id": 123,
            "status": "success",
            "count": 42,
        },
    })
    print("status_code:", resp.status_code)
    print("response:   ", resp.json())
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    print("PASS\n")


if __name__ == "__main__":
    # test_log_only()
    # test_custom_timestamp()
    # test_screenshot_missing_url()
    # test_log_with_data()
    # 截圖測試需要 Playwright chromium，視需求開啟
    test_log_with_screenshot()
    print("所有測試通過")

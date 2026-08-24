# py3_record_proj
紀錄 log. 對應圖片. 測試排程做了什麼.

## 架構

- FastAPI 接收 log,依時間寫入固定 20 分鐘區間的 txt 檔 (`data/logs/YYYY-MM-DD/HHMM-HHMM.txt`)
- 呼叫時帶 `screenshot: true` 與 `url`,會用 Playwright 截圖存到 `data/screenshots/YYYY-MM-DD/`,並在該筆 log 內註記截圖檔名
- 每個時間區間第一筆 log 進來時才會建立對應的 txt 檔

## 安裝

```bash
pip install -r requirements.txt
playwright install chromium
```

## 執行

```bash
uvicorn app.main:app --reload
```

## API

`POST /api/log`

```json
{
  "message": "任務執行完成",
  "screenshot": true,
  "url": "https://example.com"
}
```

`timestamp` 可選 (ISO 格式字串),不帶則用伺服器當下時間。

回應:

```json
{
  "status": "ok",
  "log_file": "1000-1020.txt",
  "screenshot_file": "1000-1020_101005.png"
}
```

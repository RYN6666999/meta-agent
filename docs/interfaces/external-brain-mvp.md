# 外掛大腦 MVP 介面規格

## 目標
讓任何外部工具可以透過標準 HTTP 直接使用 meta-agent 的記憶能力，而不必依賴 MCP 客戶端。

## Endpoints
- `POST /api/v1/query`
  輸入：`q`, `mode`
  輸出：搜尋結果與時間戳

- `POST /api/v1/ingest`
  輸入：`content`, `mem_type`, `title`
  輸出：ingest 結果與成功訊息

- `GET /api/v1/rules`
  輸入：`category`
  輸出：law.json 指定分類

- `POST /api/v1/log-error`
  輸入：`root_cause`, `solution`, `topic`, `context`
  輸出：error-log 寫入結果

- `GET /api/v1/health`
  輸出：API、自身、最近 health check、最近 E2E 狀態

- `GET /api/v1/trace`
  輸入：`topic`
  輸出：truth-source / error-log / pending-decisions 中與主題相關的來源片段

## 認證
- Header：`Authorization: Bearer <META_AGENT_API_KEY>`
- 開發期可用 `.env` 中 `META_AGENT_API_KEY` 控制

## 驗證
- 啟動：`python -m uvicorn api.server:app --host 127.0.0.1 --port 9901`
- Smoke test：`python scripts/test_api.py --base-url http://127.0.0.1:9901`

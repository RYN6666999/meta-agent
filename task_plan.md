# D3 External Brain Plan

## Goal
把 meta-agent 從內部自動化工具收斂成可對外掛接、可查詢、可 ingest、可觀測的外掛大腦 MVP。

## Phases
| Phase | Status | Outcome |
|------|--------|---------|
| 1. Gap analysis | completed | 盤點與商業級記憶方案的能力落差 |
| 2. MVP spec | completed | 定義第一版外掛大腦 API 與驗證方式 |
| 3. Interface implementation | completed | 建立可對外呼叫的 HTTP API 層 |
| 4. Verification | completed | 啟動 API、跑 smoke test、更新狀態檔 |

## Decisions
- 先做 HTTP API wrapper，不重寫 memory-mcp 核心邏輯。
- 先做 API key 認證，不引入 OAuth。
- 先複用既有 system-status.json 作為健康狀態來源。

## Risks
- `.venv` 原本近乎空白，需要補安裝 API 依賴。
- `memory-mcp/server.py` 不是合法 Python package 名稱，API 層需動態載入。
- 若外部服務未先跑健康檢查，`health` 端點只能回報最後一次狀態快照。
- API 現在依賴 `.env` 中既有 API key 欄位；若未來正式對外，應改成獨立 `META_AGENT_API_KEY`。

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 查詢 decision/* 分支 pattern 失敗 | 1 | 改用 `git for-each-ref` |
| Python 環境起初被視為 system | 1 | 用 Pylance 確認工作區實際 env 為 `.venv/bin/python` |
| Python 片段執行工具被取消 | 1 | 改用 `.venv/bin/python` 直接驗證 import |

## Verification
- `.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 9901` 啟動成功。
- `scripts/test_api.py` 驗證 `health`、`rules`、`query`、`trace` 全部 HTTP 200。
- `memory/system-status.json` 已新增 `api_health` 狀態快照。

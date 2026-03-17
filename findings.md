# Findings

## Current strengths
- 記憶核心已具備：`query_memory`、`ingest_memory`、`get_rules`、`log_error` 都已存在於 `memory-mcp/server.py`。
- PDCA 閉環已具備：health check、E2E、handoff 都能寫 machine-readable 狀態檔。
- decision inbox + truth-source 已形成「重要變更需升級成歷史決策」的流程。

## Commercial-grade gaps
- 缺少對外 HTTP API，外部工具無法直接查詢/寫入記憶。
- 缺少統一身份認證與可觀測 API 健康狀態。
- 缺少多來源標準化入口與 provenance/trace 介面。
- 記憶品質 metadata 仍偏弱，尚未有 confidence、usage_count 等欄位。

## MVP implementation choice
- 以 FastAPI 實作第一版外掛大腦介面層。
- 先暴露 `query`、`ingest`、`rules`、`log-error`、`health`、`trace` 六類能力。
- 先用 API key 保護，再由 n8n / CLI / 其他工具統一透過 HTTP 介接。

## Verification result
- API server 已在本機以 uvicorn 成功啟動。
- smoke test 驗證 `health`、`rules`、`query`、`trace` 全部通過。
- `trace` 已能把 `truth-source`、`pending-decisions`、`milestone-judge-log` 串成可讀溯源結果。

## Gap Convergence Round (2026-03-17)

### Gap: 驗證可靠度指標缺口
- Options: A(只保留 ok/fail) / B(在 health+e2e 增加連續失敗與恢復時間) / C(外接 Prometheus 後再做)
- Score: impact=5, effort=2, risk=1, time=1
- Decision: 採用 B，先在 `system-status.json` 補齊商業級最小可觀測欄位。

### Gap: 失敗自動恢復鏈缺口
- Options: A(只寫錯誤日誌) / B(e2e 失敗自動 truth-xval + reactivate_webhooks) / C(人工觸發)
- Score: impact=5, effort=2, risk=2, time=1
- Decision: 採用 B，符合 law.json 硬規則，避免故障卡住。

### Gap: 驗證守門缺口
- Options: A(維持手動執行) / B(建立 pre-merge smoke gate) / C(每次都跑全量回歸)
- Score: impact=4, effort=2, risk=1, time=2
- Decision: 下一步採用 B，先上最小守門，再視穩定度擴充。

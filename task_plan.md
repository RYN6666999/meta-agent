# D7 Hardening Execution Plan

## Goal
補齊商業化剩餘缺口：`D5-4` 結構化 query 輸出 + `D4-5` project-golem 掛載驗證。

## Phases
| Phase | Status | Outcome |
|------|--------|---------|
| 1. D5-4 結構化 query | completed | `query_memory_structured()` + `/api/v1/query` JSON 欄位 |
| 2. 向下相容保留 | completed | MCP `query_memory` 仍維持文字輸出，不破壞既有流程 |
| 3. D4-5 golem MCP 掛載 | completed | `project-golem` 的 `memory-mcp` 已 `✓ Connected` |
| 4. 驗證與同步計畫 | in_progress | 靜態檢查通過，待完成 smoke 與 handoff 同步 |

## Decisions
- API 端優先讀結構化 payload；若 backend 舊版則 fallback 文字模式。
- 維持 `memory-mcp` 工具介面穩定，避免外部 MCP 客戶端破壞性升級。
- 對 `project-golem` 直接做 project-scope MCP 掛載，先打通共享後端路徑。

## Risks
- `rerank_candidates` 目前仍是本地 heuristic，非 cross-encoder。
- 多租戶目前屬軟隔離，仍需 namespace-level hard isolation。

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 無阻塞錯誤 | 1 | 直接落地 D5-4 與 D4-5，靜態檢查先通過 |

## Verification
- `get_errors`：`api/server.py`、`memory-mcp/server.py`、`scripts/test_api.py` 無錯。
- `claude mcp list`（在 project-golem）顯示 `memory-mcp ... ✓ Connected`。
- 待執行：`scripts/test_api.py` 重新驗證 `query` 結構化欄位。

## Next Actions
- 補跑完整 smoke test，確認 `query` 一定回傳 `rerank_candidates`/`memory_boost_updated`。
- 將 D7 結果回寫最新 handoff，確保中斷可續跑。

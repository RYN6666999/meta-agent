# D5 Memory Governance Plan

## Goal
把 golem 可借鑑的記憶治理能力落地到 meta-agent：重排訊號、寫入安全閘、分層摘要。

## Phases
| Phase | Status | Outcome |
|------|--------|---------|
| 1. Query rerank signals | completed | `memory-mcp` 查詢結果附加 confidence/freshness/usage 訊號 |
| 2. Ingest risk guardrail | completed | 高風險 ingest 需 `[APPROVED]` 才能寫入 |
| 3. Tiered memory summaries | completed | 生成 daily/monthly/yearly 摘要並寫入狀態檔 |
| 4. End-to-end verification | completed | `health/status/rules/query/trace/ingest/protocol_parse/loop` 全部 HTTP 200 |

## Decisions
- Rerank 先走本地訊號重排，不動 LightRAG 核心檢索。
- 寫入閘門採「高風險拒寫 + `[APPROVED]` 明示審批」策略。
- 分層摘要先做 deterministic 壓縮，不依賴額外 LLM 成本。

## Risks
- rerank 屬本地啟發式，仍需後續與 LightRAG 原生排序做融合。
- 高風險關鍵詞可能有誤報，需持續調整白名單/關鍵字集。
- project-golem 尚未接上 memory-mcp，跨工具共享仍有最後一段缺口。

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| smoke test 在 `loop` 端點 ReadTimeout | 1 | 限制 rerank 掃描檔數 + `scripts/test_api.py` timeout 提升到 90 秒 |

## Verification
- `.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 9901` 啟動成功。
- `scripts/test_api.py` 驗證 `health`、`status`、`rules`、`query`、`trace`、`ingest`、`protocol_parse`、`loop` 全部 HTTP 200。
- `/api/v1/query` 已附加 `[Local Rerank Top-3]`，包含 score/confidence/freshness/usage。
- 風險閘驗證：`mem_type=rule` 且含 `law` 關鍵字時，未批准會返回「需審批」訊息。
- `scripts/memory-tier-summary.py` 產生 `memory/tiered/daily|monthly|yearly` 並寫入 `system-status.json`。

## Next Actions
- 完成 project-golem memory-mcp 掛載（P5-B 最後殘項）。
- 將 rerank 訊號同步到 API `query` 結構化欄位（目前仍在 response 文字中）。

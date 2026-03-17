# D10 Verification Stability Plan

## Mission Alignment
以用戶視角優先確保：系統可判斷、可恢復、可追溯。先穩定驗證鏈路，再擴充能力。

## Live Baseline (2026-03-17)
- health：全綠（LightRAG / n8n / Groq 全部 pass）
- e2e：local-memory-extract pass（title quality pass）
- n8n / Groq：可用（pass）
- 來源：`memory/system-status.json` 2026-03-17 14:17 已更新

## User-Scenario Objectives
| Scenario | User expectation | SLO target |
|---|---|---|
| 對話中斷後續跑 | 5 分鐘內知道下一步 | handoff 新鮮度 <= 10 分鐘 |
| 送出記憶萃取 | 不要 silent fail | e2e 成功率 >= 95% / 日 |
| 查詢歷史與規則 | 回應可追溯 | trace 命中率 >= 95% |
| 服務異常時 | 先告警再修復 | 偵測延遲 <= 5 分鐘 |

## Execution Phases
| Phase | Status | Goal | Validation | Rollback |
|---|---|---|---|---|
| P1 故障止血 | done | 確認 n8n SQLite 損毀影響範圍，恢復 e2e | `scripts/e2e_test.py` 連續通過 | 回退到前一份可用 DB 備份 |
| P2 健康穩定化 | done | 降低 LightRAG timeout，完成可用性基線 | `scripts/health_check.py` 全綠 | 使用保守 timeout 與重試策略 |
| P3 驗證守門 | not_started | 建立 pre-merge smoke gate | health+e2e 皆 pass 才允許發布 | 關閉 gate，回手動審核 |
| P4 可觀測增強 | in_progress | status 加入失敗連續次數與 MTTR | `memory/system-status.json` 欄位齊全 | 保留舊欄位相容輸出 |

## Week-1 Runbook (Practical)
1. 每日上午先跑 health + e2e，更新狀態檔與錯誤日誌。
2. 若 e2e fail 且含 SQLITE_CORRUPT，先執行 DB 修復路徑，不做功能開發。
3. 若 LightRAG timeout，先套重試與超時分級，確認健康恢復後再放行 ingest。
4. 每次修復必須附帶 machine-readable 狀態更新與可回放驗證結果。
5. 每日晚間生成 handoff，下一輪只從狀態檔推導 next steps。

## Deliverables
- D10-1：驗證穩定化 runbook（故障分類 + 處置流程）
- D10-2：健康與 e2e 守門規則（Fail fast）
- D10-3：狀態檔補強（連續失敗計數、最近恢復時間）
- D10-4：一週穩定性報告（成功率、MTTR、主要根因）

## Immediate Next Step
完成 P3 驗證守門（pre-merge gate）：把 health+e2e 綁入單一 smoke command，失敗即阻擋發布。

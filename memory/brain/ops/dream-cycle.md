# Dream Cycle 操作手冊

## 什麼是 Dream Cycle
每晚 02:00 自動執行的知識維護循環，替代原本 6 個獨立 launchd agent。

## 手動觸發
```bash
# 立即執行（health/e2e 失敗後、或手動維護）
bash /Users/ryan/meta-agent/scripts/dream-cycle.sh

# 查看執行日誌
tail -f /Users/ryan/meta-agent/memory/dream-cycle.log
```

## 執行順序
1. `truth-xval.py` — 知識圖譜交叉查核
2. `dedup-lightrag.py --dry-run` — 去重（dry-run，不破壞）
3. `memory-decay.py` — 清洗過期記憶
4. `memory-tier-summary.py` — 分層摘要
5. `obsidian-ingest.py` — Obsidian 增量 ingest
6. `persona_tech_radar.py` — 人格庫技術雷達
7. `reactivate_webhooks.py` — webhook 重新激活
8. `brain/inbox/ 清理` — 7 天以上未處理項目歸檔
9. `generate-handoff.py` — 更新 latest-handoff.md（最後執行）

## 整合前 vs 整合後

| 整合前 | 整合後 |
|--------|--------|
| 6 個各自排程的 launchd agent | 1 個 dream-cycle（每晚 02:00）|
| 無法保證執行順序 | 固定順序，前一步失敗繼續下一步 |
| 各自的 log | 統一 `memory/dream-cycle.log` |

## 保留獨立 launchd 的（有即時性需求）
| Agent | 頻率 | 原因 |
|-------|------|------|
| mobile-bridge | 服務本身 | 必須即時 |
| mobile-watchdog | 每 60 秒 | 守護服務 |
| git-score | 每小時 | 自動備份評分 |
| swap-monitor | 每 30 秒 | 系統資源監控 |
| health-check | 每天 08:00 | 早晨健康報告 |
| generate-handoff | 定時+on-stop | 也被 on-stop.py 觸發，保持獨立 |
| truth-xval | 按需 | 也被 health 失敗觸發，保持獨立 |

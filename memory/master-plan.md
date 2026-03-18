---
date: 2026-03-18
type: verified_truth
status: active
last_triggered: 2026-03-18
base_score: 180.0
usage_count: 1
expires_after_days: 365
source: plan remediation + intent realignment
last_updated: 2026-03-18 03:20
---

# meta-agent Master Plan（整改版）

## 北極星目標
建立可商業化的外掛大腦：
1. 對話中斷不失憶。
2. bug 修復後可追溯、可備份、可擴充真理源。
3. 重大變更不漏判、不漏備份。
4. 知識圖譜可持續維護，品質可觀測。

## 非可選路由（硬規則）
1. bug 修復結案：必走 `bug-closeout-autopipeline`。
2. 變更含 `api/`、`scripts/`、`law.json`：必走 `major-change-autogit-guard`。
3. health/e2e 任一失敗：必補跑 `kg-maintenance-loop`。
4. 每輪收尾：必刷新 handoff 與 machine-readable status。

## 現況摘要（2026-03-18）
- 基礎能力：P0-P5 已落地（對話連續性、記憶萃取、搜尋決策、遺忘引擎、矛盾檢查、共用 MCP）。
- API 能力：D3-D6 已完成（HTTP API、rate-limit、usage、metadata、多租戶軟隔離）。
- 自動化能力：D8-D9 已完成（人格庫定時、on-stop 萃取修復、Obsidian 增量 ingest）。
- 主要風險：流程「有能力但常忘記觸發」，導致 closeout/備份/KG 維護不穩定。

## 已完成里程碑（濃縮）
- P0-P5：核心記憶系統與自動萃取完成。
- D3：外掛大腦 MVP API 完成（query/ingest/rules/log-error/health/trace）。
- D4-D6：商業級補強完成（usage/rate-limit/status/multi-tenant/tiered-summary）。
- D8-D9：人格庫與觸發機制強化完成（技術雷達 + Obsidian ingest + on-stop 修復）。

## Top 3 未收斂缺口（現在優先）

### Gap-1｜Bug Closeout 一致性（P0）
- 問題：修完 bug 後，error-log / truth-source / git backup / xval 常有漏步。
- 目標：100% bug fix 都走單一 closeout pipeline。
- 驗證：抽樣最近 5 次 bug 修復，closeout 完整率需達 5/5。
- 執行：
  - 固定命令：
    `python3 scripts/bug_closeout.py --topic ... --summary ... --root-cause ... --fix ... --verify ...`

### Gap-2｜重大變更 guard 命中率（P0）
- 問題：重大變更常忘了先 milestone-judge + git-score。
- 目標：涉及 `api/`、`scripts/`、`law.json` 的變更，guard 命中率 100%。
- 驗證：每次變更後都可在 `memory/milestone-judge-log.md` 與 `memory/git-score-log.md` 對應到同輪紀錄。
- 執行：
  - 固定命令：
    `python3 scripts/major_change_guard.py --topic ... --description ...`

### Gap-3｜KG 維護節律（P1）
- 問題：truth-xval / dedup 有能力，但失敗後未固定回圈。
- 目標：health/e2e 失敗後 1 輪內完成 kg 維護。
- 驗證：`system-status.truth_xval` 更新且 `memory/dedup-log.md` 有當日紀錄。
- 執行：
  - 固定命令：
    `python3 scripts/truth-xval.py && python3 scripts/dedup-lightrag.py --dry-run`

## 7 日執行板（PDCA）
1. 每次 bug 修復當輪執行 closeout，禁止延後。
2. 每次高風險或核心目錄變更，當輪執行 major-change guard。
3. 每次 health/e2e 失敗，當輪執行 kg maintenance loop。
4. 每日最後一輪刷新 handoff，確認「下一步」由未完成項目動態推導。

## 驗證 KPI（machine-readable 導向）
- `bug_closeout_completeness`: 本週目標 >= 95%
- `major_change_guard_hit_rate`: 本週目標 = 100%
- `kg_maintenance_after_failure`: 本週目標 = 100%
- `handoff_freshness`: 每日最後一輪更新（目標 7/7）

## 指令速查
- closeout: `python3 scripts/bug_closeout.py --topic ... --summary ... --root-cause ... --fix ... --verify ...`
- major-guard: `python3 scripts/major_change_guard.py --topic ... --description ...`
- kg-loop: `python3 scripts/truth-xval.py && python3 scripts/dedup-lightrag.py --dry-run`
- handoff: `python3 scripts/generate-handoff.py`

## 交接規則
- 本檔只保留「仍影響決策的現況 + 未收斂缺口 + 可執行命令」。
- 已完成的歷史細節保留在 error-log / truth-source / docs，避免主計劃再次膨脹。

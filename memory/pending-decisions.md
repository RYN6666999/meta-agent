# 決策收件匣 — Pending Decisions

> AI 自動偵測高影響變更，列入此表供人類判斷。
> 確認後說 **「approve {topic}」** → AI 執行分支建立 + truth-source 記錄。
>
> ⚠️ **容量規則（GBrain inbox 原則）**：
> - 上限 **10 條 pending**。滿了就處理，禁止繼續塞。
> - `auto-git-score` 類型的例行備份不進此表（只記 law.json 變更、重大決策）。
> - 超過 7 天未處理 → dream-cycle 自動歸檔到 `memory/archive/`。
> - 完整歷史：`memory/archive/pending-decisions-archive-2026-04-23.md`

| date | topic | description | score | signals | status |
|------|-------|-------------|-------|---------|--------|
| 2026-04-17 | crm-esmodule-refactor | crm.js 5062行拆分為 src/ ES Module 樹，navigate()修復，日報 [working-tree] | 100 | 其他變更 memory/handoff/generate-handoff.log +10; 其他變更 memory/handoff/latest-handoff.md +10 | pending |
| 2026-04-21 | tong-jincheng-perspective | .agents/skills 新增 tong-jincheng-perspective skill | 380 | 其他變更 .agents/skills/tong-jincheng-perspective/LICENSE +10 | pending |
| 2026-04-23 | mobile-bridge-root-cause | uvicorn 36天無法啟動根因確認：memory-mcp/ 路徑不符，每日產生69個假陽性error-log，symlink修復完成 [working-tree] | 200 | brain/bugs/mobile-bridge.md 蒸餾 69 error-log; memory/handoff/latest-handoff.md | pending |
<!-- AI 偵測到重大決策時，自動在此插入列（上限 10 條 pending，滿了先清） -->
| 2026-04-24 | auto-git-score | git-score 自動 commit（score=150），含重要變更 [commit:HEAD~1..HEAD] | 140 | error-log 新增根因 error-log/2026-04-24-health-check.md +50; 其他變更 memory/dedup-log.md +10 | pending |

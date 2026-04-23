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
| 2026-03-16 | pdca-causal-chain | commit後里程碑裁判寫入決策匣，驗證前後節點閉環 [commit:HEAD~1..HEAD] | 100 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/system-status.json +10 | done:decision/pdca-causal-chain-2026-03-16 |
| 2026-03-16 | health-title-restored | D1/D2 修復：Groq 健康檢查誤判消除 + memory-extract 標題品質恢復 7 [working-tree] | 180 | 其他變更 memory/git-score-log.md +10; 其他變更 memory/git-score.log +10 | done:decision/health-title-restored-2026-03-16 |
| 2026-03-16 | auto-git-score | git-score 自動 commit（score=55），含重要變更 [commit:HEAD~1..HEAD] | 180 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/milestone-judge-log.md +10 | done:decision/auto-git-score-2026-03-16 |
| 2026-04-17 | crm-esmodule-refactor | crm.js 5062行拆分為 src/ ES Module 樹，navigate()修復，日報 [working-tree] | 100 | 其他變更 memory/handoff/generate-handoff.log +10; 其他變更 memory/handoff/latest-handoff.md +10 | pending |
| 2026-04-21 | tong-jincheng-perspective | .agents/skills 新增 tong-jincheng-perspective skill | 380 | 其他變更 .agents/skills/tong-jincheng-perspective/LICENSE +10 | pending |
| 2026-04-23 | mobile-bridge-root-cause | 蒸餾 69 個 error-log → brain/bugs/mobile-bridge.md，確認 cloudflared 才是根因 | 200 | brain/ 新架構建立 | pending |
<!-- AI 偵測到重大決策時，自動在此插入列（上限 10 條 pending，滿了先清） -->
| 2026-04-23 | mobile-bridge-root-cause | uvicorn 36天無法啟動，每日產生69個假陽性error-log [working-tree] | 200 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/milestone-judge-log.md +10 | pending |

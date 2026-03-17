# 決策收件匣 — Pending Decisions

> AI 自動偵測高影響變更，列入此表供人類判斷。
> 確認後說 **「approve {topic}」** → AI 執行分支建立 + truth-source 記錄。

| date | topic | description | score | signals | status |
|------|-------|-------------|-------|---------|--------|
| 2026-03-16 | pdca-causal-chain | commit後里程碑裁判寫入決策匣，驗證前後節點閉環 [commit:HEAD~1..HEAD] | 100 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/system-status.json +10 | done:decision/pdca-causal-chain-2026-03-16 |
| 2026-03-16 | health-title-restored | D1/D2 修復：Groq 健康檢查誤判消除 + memory-extract 標題品質恢復 7 [working-tree] | 180 | 其他變更 memory/git-score-log.md +10; 其他變更 memory/git-score.log +10 | done:decision/health-title-restored-2026-03-16 |
| 2026-03-16 | auto-git-score | git-score 自動 commit（score=55），含重要變更 [commit:HEAD~1..HEAD] | 180 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/milestone-judge-log.md +10 | done:decision/auto-git-score-2026-03-16 |
| 2026-03-17 | auto-git-score | git-score 自動 commit（score=160），含重要變更 [commit:HEAD~1..HEAD] | 410 | 其他變更 api/agent_loop.py +10; 其他變更 api/server.py +10 | pending |
<!-- AI 偵測到重大決策時，自動在此插入列 -->


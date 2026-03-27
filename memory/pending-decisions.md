# 決策收件匣 — Pending Decisions

> AI 自動偵測高影響變更，列入此表供人類判斷。
> 確認後說 **「approve {topic}」** → AI 執行分支建立 + truth-source 記錄。

| date | topic | description | score | signals | status |
|------|-------|-------------|-------|---------|--------|
| 2026-03-16 | pdca-causal-chain | commit後里程碑裁判寫入決策匣，驗證前後節點閉環 [commit:HEAD~1..HEAD] | 100 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/system-status.json +10 | done:decision/pdca-causal-chain-2026-03-16 |
| 2026-03-16 | health-title-restored | D1/D2 修復：Groq 健康檢查誤判消除 + memory-extract 標題品質恢復 7 [working-tree] | 180 | 其他變更 memory/git-score-log.md +10; 其他變更 memory/git-score.log +10 | done:decision/health-title-restored-2026-03-16 |
| 2026-03-16 | auto-git-score | git-score 自動 commit（score=55），含重要變更 [commit:HEAD~1..HEAD] | 180 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/milestone-judge-log.md +10 | done:decision/auto-git-score-2026-03-16 |
| 2026-03-17 | auto-git-score | git-score 自動 commit（score=160），含重要變更 [commit:HEAD~1..HEAD] | 410 | 其他變更 api/agent_loop.py +10; 其他變更 api/server.py +10 | pending |
| 2026-03-17 | auto-git-score | git-score 自動 commit（score=235），含重要變更 [commit:HEAD~1..HEAD] | 510 | 其他變更 common/debug_solver.py +10; 其他變更 common/ig_discuss.py +10 | pending |
| 2026-03-17 | auto-git-score | git-score 自動 commit（score=115），含重要變更 [commit:HEAD~1..HEAD] | 290 | 其他變更 error-log/2026-03-17-health-check.md +10; law.json forbidden規則變更 +80 | pending |
| 2026-03-17 | auto-git-score | git-score 自動 commit（score=220），含重要變更 [commit:HEAD~1..HEAD] | 580 | 其他變更 api/server.py +10; 其他變更 docs/interfaces/external-brain-mvp.md +10 | pending |
| 2026-03-18 | auto-git-score | git-score 自動 commit（score=175），含重要變更 [commit:HEAD~1..HEAD] | 260 | 其他變更 error-log/2026-03-17-mobile-bridge-api-down.md +10; error-log 新增根因 error-log/2026-03-18-mobile-bridge-api-down.md +50 | pending |
| 2026-03-18 | auto-git-score | git-score 自動 commit（score=120），含重要變更 [commit:HEAD~1..HEAD] | 240 | 其他變更 api/server.py +10; 其他變更 common/code_intelligence.py +10 | pending |
| 2026-03-18 | auto-git-score | git-score 自動 commit（score=175），含重要變更 [commit:HEAD~1..HEAD] | 500 | 其他變更 .claude/skills/bug-closeout-autopipeline/SKILL.md +10; 其他變更 .claude/skills/daily-resume-pdca/SKILL.md +10 | pending |
| 2026-03-18 | auto-git-score | git-score 自動 commit（score=115），含重要變更 [commit:HEAD~1..HEAD] | 250 | 其他變更 docs/architecture-debt-analysis.md +10; 其他變更 docs/mission-verification.md +10 | pending |
| 2026-03-18 | auto-git-score | git-score 自動 commit（score=100），含重要變更 [commit:HEAD~1..HEAD] | 200 | 其他變更 docs/project-execution-flow.md +10; 其他變更 docs/project-execution-flow.mmd +10 | pending |
| 2026-03-19 | auto-git-score | git-score 自動 commit（score=170），含重要變更 [commit:HEAD~1..HEAD] | 190 | 其他變更 docs/zero-trust-rebuild-diagrams.html +10; 其他變更 docs/zero-trust-rebuild-plan.md +10 | pending |
| 2026-03-19 | auto-git-score | git-score 自動 commit（score=160），含重要變更 [commit:HEAD~1..HEAD] | 150 | error-log 新增根因 error-log/2026-03-19-health-check.md +50; 其他變更 error-log/2026-03-19-mobile-bridge-api-down.md +10 | pending |
| 2026-03-20 | auto-git-score | git-score 自動 commit（score=60），含重要變更 [commit:HEAD~1..HEAD] | 90 | 其他變更 error-log/2026-03-19-mobile-bridge-api-down.md +10; error-log 新增根因 error-log/2026-03-20-mobile-bridge-api-down.md +50 | pending |
| 2026-03-20 | auto-git-score | git-score 自動 commit（score=110），含重要變更 [commit:HEAD~1..HEAD] | 100 | error-log 新增根因 error-log/2026-03-20-health-check.md +50; 其他變更 error-log/2026-03-20-mobile-bridge-api-down.md +10 | pending |
| 2026-03-20 | auto-git-score | git-score 自動 commit（score=110），含重要變更 [commit:HEAD~1..HEAD] | 190 | 其他變更 docs/bdd-guidelines.md +10; 其他變更 docs/tdd-guidelines.md +10 | pending |
| 2026-03-21 | auto-git-score | git-score 自動 commit（score=125），含重要變更 [commit:HEAD~1..HEAD] | 210 | error-log 新增根因 error-log/2026-03-21-mobile-bridge-api-down.md +50; error-log 新增根因 error-log/2026-03-21-mobile-bridge-tunnel-down.md +50 | pending |
| 2026-03-21 | auto-git-score | git-score 自動 commit（score=135），含重要變更 [commit:HEAD~1..HEAD] | 130 | 其他變更 crm/index.html +10; error-log 新增根因 error-log/2026-03-21-health-check.md +50 | pending |
| 2026-03-21 | auto-git-score | git-score 自動 commit（score=100），含重要變更 [commit:HEAD~1..HEAD] | 120 | 其他變更 .claude/launch.json +10; 其他變更 .claude/skills/frontend-design/SKILL.md +10 | pending |
| 2026-03-21 | auto-git-score | git-score 自動 commit（score=95），含重要變更 [commit:HEAD~1..HEAD] | 90 | 其他變更 error-log/2026-03-21-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-21-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-21 | auto-git-score | git-score 自動 commit（score=85），含重要變更 [commit:HEAD~1..HEAD] | 850 | 其他變更 error-log/2026-03-21-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-21-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-22 | auto-git-score | git-score 自動 commit（score=250），含重要變更 [commit:HEAD~1..HEAD] | 260 | 其他變更 error-log/2026-03-21-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-21-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-22 | auto-git-score | git-score 自動 commit（score=80），含重要變更 [commit:HEAD~1..HEAD] | 90 | 其他變更 error-log/2026-03-22-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-22-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-22 | auto-git-score | git-score 自動 commit（score=80），含重要變更 [commit:HEAD~1..HEAD] | 70 | 其他變更 error-log/2026-03-22-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-22-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-23 | auto-git-score | git-score 自動 commit（score=200），含重要變更 [commit:HEAD~1..HEAD] | 220 | 其他變更 error-log/2026-03-22-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-22-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-23 | auto-git-score | git-score 自動 commit（score=165），含重要變更 [commit:HEAD~1..HEAD] | 160 | error-log 新增根因 error-log/2026-03-23-health-check.md +50; 其他變更 error-log/2026-03-23-mobile-bridge-api-down.md +10 | pending |
| 2026-03-23 | auto-git-score | git-score 自動 commit（score=70），含重要變更 [commit:HEAD~1..HEAD] | 60 | 其他變更 error-log/2026-03-23-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-23-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=250），含重要變更 [commit:HEAD~1..HEAD] | 260 | 其他變更 error-log/2026-03-23-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-23-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=85），含重要變更 [commit:HEAD~1..HEAD] | 80 | 其他變更 error-log/2026-03-24-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-24-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=150），含重要變更 [commit:HEAD~1..HEAD] | 220 | 其他變更 .wrangler/cache/pages.json +10; 其他變更 .wrangler/cache/wrangler-account.json +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=105），含重要變更 [commit:HEAD~1..HEAD] | 170 | 其他變更 error-log/2026-03-24-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-24-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=155），含重要變更 [commit:HEAD~1..HEAD] | 280 | 其他變更 error-log/2026-03-24-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-24-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=185），含重要變更 [commit:HEAD~1..HEAD] | 280 | 其他變更 error-log/2026-03-24-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-24-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=90），含重要變更 [commit:HEAD~1..HEAD] | 110 | 其他變更 error-log/2026-03-24-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-24-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-24 | CRM-status-pill-click-無法切換 | status-pill 點擊無法循環切換狀態（高意願/觀察中/冷淡/無效） [working-tree] | 80 | 其他變更 error-log/2026-03-24-mobile-bridge-tunnel-down.md +10; 其他變更 memory/milestone-judge-log.md +10 | pending |
| 2026-03-24 | auto-git-score | git-score 自動 commit（score=80），含重要變更 [commit:HEAD~1..HEAD] | 90 | 其他變更 "error-log/2026-03-24-CRM-status-pill-click-\347\204\241\346\263\225\345\210\207\346\217\233.md" +10; 其他變更 error-log/2026-03-24-mobile-bridge-api-down.md +10 | pending |
| 2026-03-25 | auto-git-score | git-score 自動 commit（score=80），含重要變更 [commit:HEAD~1..HEAD] | 130 | error-log 新增根因 error-log/2026-03-25-mobile-bridge-api-down.md +50; error-log 新增根因 error-log/2026-03-25-mobile-bridge-tunnel-down.md +50 | pending |
| 2026-03-25 | auto-git-score | git-score 自動 commit（score=90），含重要變更 [commit:HEAD~1..HEAD] | 60 | 其他變更 error-log/2026-03-25-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-25-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-25 | auto-git-score | git-score 自動 commit（score=110），含重要變更 [commit:HEAD~1..HEAD] | 120 | error-log 新增根因 error-log/2026-03-25-health-check.md +50; 其他變更 error-log/2026-03-25-mobile-bridge-api-down.md +10 | pending |
| 2026-03-25 | auto-git-score | git-score 自動 commit（score=80），含重要變更 [commit:HEAD~1..HEAD] | 70 | 其他變更 error-log/2026-03-25-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-25-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-25 | auto-git-score | git-score 自動 commit（score=70），含重要變更 [commit:HEAD~1..HEAD] | 60 | 其他變更 error-log/2026-03-25-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-25-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-26 | auto-git-score | git-score 自動 commit（score=155），含重要變更 [commit:HEAD~1..HEAD] | 170 | 其他變更 error-log/2026-03-25-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-25-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-26 | auto-git-score | git-score 自動 commit（score=190），含重要變更 [commit:HEAD~1..HEAD] | 160 | error-log 新增根因 error-log/2026-03-26-health-check.md +50; 其他變更 error-log/2026-03-26-mobile-bridge-api-down.md +10 | pending |
| 2026-03-26 | auto-git-score | git-score 自動 commit（score=65），含重要變更 [commit:HEAD~1..HEAD] | 70 | 其他變更 error-log/2026-03-26-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-26-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-27 | auto-git-score | git-score 自動 commit（score=185），含重要變更 [commit:HEAD~1..HEAD] | 430 | 其他變更 error-log/2026-03-26-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-26-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-27 | auto-git-score | git-score 自動 commit（score=145），含重要變更 [commit:HEAD~1..HEAD] | 160 | error-log 新增根因 error-log/2026-03-27-health-check.md +50; 其他變更 error-log/2026-03-27-mobile-bridge-api-down.md +10 | pending |
| 2026-03-27 | auto-git-score | git-score 自動 commit（score=125），含重要變更 [commit:HEAD~1..HEAD] | 180 | 其他變更 error-log/2026-03-27-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-27-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-27 | auto-git-score | git-score 自動 commit（score=150），含重要變更 [commit:HEAD~1..HEAD] | 230 | 其他變更 error-log/2026-03-27-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-27-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-27 | auto-git-score | git-score 自動 commit（score=235），含重要變更 [commit:HEAD~1..HEAD] | 400 | 其他變更 error-log/2026-03-27-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-27-mobile-bridge-tunnel-down.md +10 | pending |
| 2026-03-27 | auto-git-score | git-score 自動 commit（score=65），含重要變更 [commit:HEAD~1..HEAD] | 60 | 其他變更 error-log/2026-03-27-mobile-bridge-api-down.md +10; 其他變更 error-log/2026-03-27-mobile-bridge-tunnel-down.md +10 | pending |
<!-- AI 偵測到重大決策時，自動在此插入列 -->


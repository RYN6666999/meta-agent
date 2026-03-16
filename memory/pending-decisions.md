# 決策收件匣 — Pending Decisions

> AI 自動偵測高影響變更，列入此表供人類判斷。
> 確認後說 **「approve {topic}」** → AI 執行分支建立 + truth-source 記錄。

| date | topic | description | score | signals | status |
|------|-------|-------------|-------|---------|--------|
| 2026-03-16 | pdca-causal-chain | commit後里程碑裁判寫入決策匣，驗證前後節點閉環 [commit:HEAD~1..HEAD] | 100 | 其他變更 memory/handoff/latest-handoff.md +10; 其他變更 memory/system-status.json +10 | pending |
<!-- AI 偵測到重大決策時，自動在此插入列 -->


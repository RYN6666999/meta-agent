---
date: 2026-03-16
type: verified_truth
status: active
last_triggered: 2026-03-18
usage_count: 1
base_score: 144.0
expires_after_days: 365
source: milestone-judge（自動生成）
branch: decision/bug-fixes-and-automation-loop-2026-03-16
score: 150
---

# bug-fixes-and-automation-loop

## 描述
修復 4 個核心 bug：git-score filepath 解析、LightRAG 自動 ingest、handoff session diff、PreToolUse memory hook

## 評分信號
  其他變更 memory/handoff/latest-handoff.md +10
  其他變更 memory/turn-count.txt +10
  核心腳本變更 scripts/generate-handoff.py +40
  核心腳本變更 scripts/on-stop.py +40
  其他變更 memory/ingest-tracker.json +10
  核心腳本變更 scripts/pre-tool-memory-check.py +40

**總分：150 / 閾值 60**

## 分支
`decision/bug-fixes-and-automation-loop-2026-03-16` — 此分支為本決策的真理源，供未來對照。

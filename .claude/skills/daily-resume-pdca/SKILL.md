---
name: daily-resume-pdca
version: 1.0.0
description: "Use at session start to avoid context loss. This skill provides a deterministic startup sequence from handoff to actionable top priorities."
argument-hint: "[handoff + pending + plan startup]"
---

# Daily Resume PDCA

## When to Use

- Session start
- Context-loss risk after long pause
- Need deterministic restart workflow

## Workflow

1. Read memory/handoff/latest-handoff.md
2. Read memory/pending-decisions.md
3. Read memory/master-plan.md
4. Output top 3 pending items with status
5. Pick one in-progress item and define verification command

## Recommended Commands

```bash
python3 scripts/generate-handoff.py
rg -n "| pending |" memory/pending-decisions.md
```

## Output Contract

- One prioritized in-progress task
- One verification command
- One rollback command/path

## Checklist

- Removes startup ambiguity
- Reduces repeated context reconstruction
- Keeps PDCA loop measurable

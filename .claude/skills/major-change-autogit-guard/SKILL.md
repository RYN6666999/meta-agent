---
name: major-change-autogit-guard
description: "Use when code or infra changes may be major. This skill prevents forgetting auto-backup and decision capture by enforcing milestone judge + git-score sequence."
argument-hint: "--topic <topic> --description <what changed and verified>"
---

# Major Change Autogit Guard

## When to Use

- Changes touch law.json
- Changes touch scripts/ or api/
- Changes touch truth-source/ or error-log/
- User says "major change", "important", or "high risk"

## Workflow

```bash
python3 scripts/major_change_guard.py --topic <topic> --description "<what changed and what was verified>"
```

## Rationale

- milestone-judge: routes major changes into pending-decisions for human approval
- git-score: prevents long uncommitted drift and auto-backups above threshold

## Checklist

- Confirm pending-decisions updated when score >= threshold
- Confirm git-score log has a new record
- If commit happened, ensure commit message includes score context

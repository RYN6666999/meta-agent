---
name: toolbox-ops
description: "Operate toolbox with deterministic checks: health -> execute -> truth-xval on failure -> machine-readable status."
argument-hint: "[toolbox health | douyin preflight | prune suggestions]"
---

# Toolbox Ops

## When to Use

- Daily startup checks
- Before running Douyin pipeline
- Before pruning or hiding tools in UI

## Workflow

1. Run `toolbox-health.sh`
2. If targeting Douyin, run `douyin-preflight.sh`
3. If any critical check fails, run `python3 scripts/truth-xval.py`
4. Write/refresh machine-readable reports under `memory/`
5. For cleanup proposals, run `toolbox-prune.py` (non-destructive)

## Commands

```bash
bash /Users/ryan/meta-agent/scripts/toolbox/toolbox-health.sh
bash /Users/ryan/meta-agent/scripts/toolbox/douyin-preflight.sh
python3 /Users/ryan/meta-agent/scripts/toolbox/toolbox-prune.py
python3 /Users/ryan/meta-agent/scripts/truth-xval.py
```

## Output Contract

- `memory/toolbox-health.json`
- `memory/douyin-preflight.json`
- `memory/toolbox-prune-report.json`

Never make destructive pruning changes automatically; only produce candidates.

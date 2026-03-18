---
name: kg-maintenance-loop
description: "Use when LightRAG quality or consistency is a concern. This skill enforces truth cross-validation and graph dedup maintenance in a repeatable loop."
argument-hint: "[--run-dedup]"
---

# KG Maintenance Loop

## When to Use

- "knowledge graph quality is drifting"
- "LightRAG misses known truths"
- "need periodic KG optimization"

## Workflow

```bash
python3 scripts/truth-xval.py
python3 scripts/dedup-lightrag.py --dry-run
```

Optional execution mode:

```bash
python3 scripts/dedup-lightrag.py
```

## Expected Outcomes

- truth-xval writes machine-readable status into system-status
- missing LightRAG truths are auto-repaired when possible
- dedup report is written for manual merge decisions in WebUI

## Checklist

- Keep dedup in dry-run by default
- Only run non-dry dedup when review bandwidth exists

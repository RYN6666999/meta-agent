---
name: bug-closeout-autopipeline
version: 1.0.0
description: "Use when a bug has been fixed and you must avoid memory loss. This skill enforces one-command closeout: error-log, truth-source expansion, LightRAG ingest, milestone judge, auto git-score backup, truth-xval, and KG dedup dry-run."
argument-hint: "--topic <kebab-case> --summary <text> --root-cause <text> --fix <text> --verify <text> [--skip-kg]"
---

# Bug Closeout Autopipeline

## When to Use

- "Bug fixed, close it out"
- "backup this fix and update truth source"
- "log root cause and prevent forgetting"
- Any post-fix handoff where memory continuity matters

## Workflow

```bash
python3 scripts/bug_closeout.py \
  --topic <kebab-case-topic> \
  --summary "<one-line summary>" \
  --root-cause "<root cause>" \
  --fix "<fix details>" \
  --verify "<verification command or proof>"
```

Optional:

```bash
python3 scripts/bug_closeout.py ... --skip-kg
```

## Guarantees

- Writes one record to error-log
- Writes one verified entry to truth-source
- Tries LightRAG ingest for that truth record (non-blocking)
- Runs milestone judge to pending-decisions
- Runs git-score auto backup
- Runs truth-xval cross validation
- Runs dedup-lightrag dry-run unless skipped

## Checklist

- [ ] Topic uses kebab-case
- [ ] Root cause is specific and falsifiable
- [ ] Verification line references a real command/output
- [ ] Closeout command completed with no hard error
- [ ] If pending-decision generated, request human approve/reject

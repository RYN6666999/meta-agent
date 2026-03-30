---
description: Generate non-destructive prune suggestions for toolbox tools.
---

Run:

```bash
python3 /Users/ryan/meta-agent/scripts/toolbox/toolbox-prune.py
```

Then summarize:
- hide candidates
- keep list
- which dependency is down

Never modify source files directly in this command; only emit report.
Source of truth: `/Users/ryan/meta-agent/memory/toolbox-prune-report.json`.

#!/usr/bin/env python3
"""
Generate an action strategy from memory history JSONL.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

TARGETS = ["vscode_gb", "comet_gb", "claude_gb", "openclaw_gb"]


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def collect_vscode_extensions(rows: list[dict]) -> Counter:
    c = Counter()
    for row in rows:
        for p in row.get("top_processes", []):
            args = str(p.get("args", ""))
            if "/Users/" not in args or "/.vscode/extensions/" not in args:
                continue
            marker = "/.vscode/extensions/"
            i = args.find(marker)
            if i < 0:
                continue
            remain = args[i + len(marker):]
            ext = remain.split("/", 1)[0]
            if ext:
                c[ext] += 1
    return c


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate strategy from memory history")
    parser.add_argument("--input", default="memory/mem-history.jsonl")
    parser.add_argument("--output", default="memory/mem-strategy-latest.md")
    parser.add_argument("--threshold", type=float, default=4.0)
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"input not found: {src}")

    rows = load_rows(src)
    if not rows:
        raise SystemExit("no valid rows")

    peaks = {k: (-1.0, "") for k in TARGETS}
    over = {k: [] for k in TARGETS}

    for row in rows:
        ts = row.get("ts", "")
        totals = row.get("totals", {})
        for k in TARGETS:
            v = float(totals.get(k, 0.0) or 0.0)
            if v > peaks[k][0]:
                peaks[k] = (v, ts)
            if v >= args.threshold:
                over[k].append((ts, v))

    ext_counter = collect_vscode_extensions(rows)
    top_ext = ext_counter.most_common(5)

    top_target = max(TARGETS, key=lambda k: peaks[k][0])
    top_value, top_ts = peaks[top_target]

    lines = []
    lines.append("# Memory Strategy Report")
    lines.append("")
    lines.append(f"samples: {len(rows)}")
    lines.append(f"threshold_gb: {args.threshold:.2f}")
    lines.append("")
    lines.append("## Peaks")
    for k in TARGETS:
        v, ts = peaks[k]
        lines.append(f"- {k}: {v:.3f} GB at {ts}")

    lines.append("")
    lines.append("## Threshold Hits")
    for k in TARGETS:
        lines.append(f"- {k}: {len(over[k])} hits")

    lines.append("")
    lines.append("## Suggested Actions")

    if top_target == "vscode_gb":
        lines.append("- Priority 1: Reduce VS Code extension and language-server pressure during heavy runs.")
        lines.append("- Action: Keep python.analysis.diagnosticMode=openFilesOnly and indexing disabled in workspace settings.")
        lines.append("- Action: During critical runs, close non-essential VS Code windows and notebooks.")
        if top_ext:
            lines.append("- Candidate extension processes to disable in this workspace:")
            for ext, count in top_ext:
                lines.append(f"  - {ext} (observed {count} samples)")

    if peaks["comet_gb"][0] >= max(2.0, args.threshold * 0.5):
        lines.append("- Priority 2: Comet renderer fan-out is visible; reduce open Comet tabs and extension pages during coding runs.")
        lines.append("- Action: Keep only one active Comet workspace/session while benchmarks or E2E run.")

    if any(len(over[k]) > 0 for k in TARGETS):
        lines.append("- Priority 3: Add automatic kill/restart policy when any target exceeds threshold for consecutive samples.")

    lines.append("")
    lines.append("## Dominant Spike")
    lines.append(f"- target: {top_target}")
    lines.append(f"- peak_gb: {top_value:.3f}")
    lines.append(f"- timestamp: {top_ts}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()

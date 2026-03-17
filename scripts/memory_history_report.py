#!/usr/bin/env python3
"""
Summarize memory history collected by memory_history_watch.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TARGETS = ["vscode_gb", "comet_gb", "claude_gb", "openclaw_gb"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize memory history JSONL.")
    parser.add_argument("--input", default="memory/mem-history.jsonl", help="Input JSONL path.")
    parser.add_argument("--threshold", type=float, default=4.0, help="Threshold in GB.")
    args = parser.parse_args()

    p = Path(args.input)
    if not p.exists():
        raise SystemExit(f"input not found: {p}")

    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not rows:
        raise SystemExit("no valid rows")

    peaks = {k: (-1.0, None) for k in TARGETS}
    over = {k: [] for k in TARGETS}

    for row in rows:
        ts = row.get("ts")
        totals = row.get("totals", {})
        for key in TARGETS:
            val = float(totals.get(key, 0.0) or 0.0)
            if val > peaks[key][0]:
                peaks[key] = (val, ts)
            if val >= args.threshold:
                over[key].append((ts, val))

    print(f"samples={len(rows)}")
    for key in TARGETS:
        peak_val, peak_ts = peaks[key]
        print(f"peak {key}: {peak_val:.3f} GB at {peak_ts}")

    print(f"\nthreshold={args.threshold:.2f} GB")
    for key in TARGETS:
        hits = over[key]
        print(f"{key}: {len(hits)} hits")
        for ts, val in hits[:10]:
            print(f"  {ts}  {val:.3f} GB")


if __name__ == "__main__":
    main()

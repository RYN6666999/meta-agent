#!/usr/bin/env python3
"""
Record per-process memory history for selected apps on macOS.

Usage examples:
  python scripts/memory_history_watch.py --duration 7200
  python scripts/memory_history_watch.py --interval 5 --duration 0 --output memory/mem-history.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

WATCH_KEYWORDS = [
    "visual studio code",
    "code helper",
    "comet",
    "claude",
    "openclaw",
    "electron",
]


def run_cmd(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def collect_process_rows() -> list[dict]:
    # rss unit is KB in ps output.
    out = run_cmd(["ps", "-Ao", "pid,rss,comm,args"])
    rows: list[dict] = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid_s, rss_s, comm, args = parts
        hay = f"{comm} {args}".lower()
        if not any(k in hay for k in WATCH_KEYWORDS):
            continue
        try:
            pid = int(pid_s)
            rss_kb = int(rss_s)
        except ValueError:
            continue
        rows.append(
            {
                "pid": pid,
                "rss_kb": rss_kb,
                "rss_gb": round(rss_kb / 1024 / 1024, 4),
                "comm": comm,
                "args": args,
            }
        )
    rows.sort(key=lambda x: x["rss_kb"], reverse=True)
    return rows


def collect_memory_pressure() -> dict:
    out = run_cmd(["memory_pressure"])
    info = {
        "system_free_percent": None,
        "swapins": None,
        "swapouts": None,
    }
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("System-wide memory free percentage:"):
            value = line.split(":", 1)[1].strip().rstrip("%")
            try:
                info["system_free_percent"] = float(value)
            except ValueError:
                pass
        elif line.startswith("Swapins:"):
            try:
                info["swapins"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("Swapouts:"):
            try:
                info["swapouts"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return info


def bucket_totals(rows: list[dict]) -> dict:
    buckets = {
        "vscode_kb": 0,
        "comet_kb": 0,
        "claude_kb": 0,
        "openclaw_kb": 0,
    }
    for row in rows:
        text = f"{row['comm']} {row['args']}".lower()
        rss = row["rss_kb"]
        if "visual studio code" in text or "code helper" in text:
            buckets["vscode_kb"] += rss
        if "comet" in text:
            buckets["comet_kb"] += rss
        if "claude" in text:
            buckets["claude_kb"] += rss
        if "openclaw" in text:
            buckets["openclaw_kb"] += rss

    return {
        "vscode_gb": round(buckets["vscode_kb"] / 1024 / 1024, 4),
        "comet_gb": round(buckets["comet_kb"] / 1024 / 1024, 4),
        "claude_gb": round(buckets["claude_kb"] / 1024 / 1024, 4),
        "openclaw_gb": round(buckets["openclaw_kb"] / 1024 / 1024, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch memory history for selected apps.")
    parser.add_argument("--interval", type=int, default=10, help="Sampling interval in seconds.")
    parser.add_argument(
        "--duration",
        type=int,
        default=3600,
        help="Total watch seconds. Use 0 for endless.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="memory/mem-history.jsonl",
        help="Output JSONL path.",
    )
    args = parser.parse_args()

    if args.interval <= 0:
        raise SystemExit("--interval must be > 0")
    if args.duration < 0:
        raise SystemExit("--duration must be >= 0")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()

    while True:
        now = datetime.now().isoformat(timespec="seconds")
        rows = collect_process_rows()
        totals = bucket_totals(rows)
        pressure = collect_memory_pressure()

        record = {
            "ts": now,
            "totals": totals,
            "memory_pressure": pressure,
            "top_processes": rows[:12],
        }

        with output_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")

        peak = max(
            totals["vscode_gb"],
            totals["comet_gb"],
            totals["claude_gb"],
            totals["openclaw_gb"],
        )
        if peak >= 4.0:
            print(f"[{now}] ALERT peak_gb={peak} totals={totals}", flush=True)

        if args.duration and (time.time() - start) >= args.duration:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Collect simple runtime benchmarks for key maintenance scripts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.config import BASE_DIR
from common.status_store import update_status

OUTPUT_JSON = BASE_DIR / "memory" / "perf-baseline-2026-03-17.json"

COMMANDS = [
    ["python3", "scripts/health_check.py"],
    ["python3", "scripts/truth-xval.py"],
]


def run_once(cmd: list[str], timeout: int = 180) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "cmd": " ".join(cmd),
        "elapsed_ms": elapsed_ms,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
    }


def benchmark(rounds: int = 3) -> dict:
    all_results: list[dict] = []
    for idx in range(rounds):
        for cmd in COMMANDS:
            item = run_once(cmd)
            item["round"] = idx + 1
            all_results.append(item)

    grouped: dict[str, list[float]] = {}
    for item in all_results:
        grouped.setdefault(item["cmd"], []).append(item["elapsed_ms"])

    summary = {}
    for cmd, values in grouped.items():
        sorted_values = sorted(values)
        mid = len(sorted_values) // 2
        p50 = sorted_values[mid]
        p95 = sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * 0.95))]
        summary[cmd] = {
            "runs": len(values),
            "p50_ms": p50,
            "p95_ms": p95,
            "min_ms": min(values),
            "max_ms": max(values),
        }

    return {
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rounds": rounds,
        "commands": COMMANDS,
        "summary": summary,
        "results": all_results,
    }


def main() -> int:
    report = benchmark()
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def mutator(status: dict) -> None:
        status["benchmark_baseline"] = {
            "ok": True,
            "collected_at": report["collected_at"],
            "file": str(OUTPUT_JSON.relative_to(BASE_DIR)),
            "summary": report["summary"],
        }

    update_status(mutator)

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"[benchmark] wrote {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

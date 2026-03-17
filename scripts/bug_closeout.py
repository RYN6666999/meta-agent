#!/usr/bin/env python3
"""
Bug closeout autopipeline.

Purpose:
- Persist bug root cause + fix into error-log.
- Expand truth-source with a verified note.
- Optionally ingest truth note to LightRAG.
- Run milestone judge (major-change decision inbox).
- Run git-score auto backup.
- Run truth-xval cross validation.
- Run KG maintenance dry-run (dedup-lightrag).

Usage example:
  python3 scripts/bug_closeout.py \
    --topic mobile-bridge-webhook-bind-failed \
    --summary "fixed webhook bind fallback and verified health" \
    --root-cause "draft webhook route mismatch" \
    --fix "normalize webhook route + restart launchd" \
    --verify "python3 scripts/mobile_bridge_acceptance.py"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERROR_LOG_DIR = ROOT / "error-log"
TRUTH_DIR = ROOT / "truth-source"
LIGHTRAG_INGEST = "http://localhost:9621/documents/text"


def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def write_error_log(topic: str, summary: str, root_cause: str, fix: str, verify: str) -> Path:
    ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = ERROR_LOG_DIR / f"{date_str}-{topic}.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = (
        f"# {topic}\n\n"
        f"- timestamp: {ts}\n"
        f"- summary: {summary}\n"
        f"- root_cause: {root_cause}\n"
        f"- fix: {fix}\n"
        f"- verify: {verify}\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def write_truth_source(topic: str, summary: str, root_cause: str, fix: str, verify: str) -> Path:
    TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = TRUTH_DIR / f"{date_str}-{topic}.md"
    body = (
        f"---\n"
        f"date: {date_str}\n"
        f"type: verified_truth\n"
        f"status: active\n"
        f"last_triggered: {date_str}\n"
        f"expires_after_days: 365\n"
        f"source: bug-closeout autopipeline\n"
        f"---\n\n"
        f"# {topic}\n\n"
        f"## Summary\n{summary}\n\n"
        f"## Root Cause\n{root_cause}\n\n"
        f"## Fix\n{fix}\n\n"
        f"## Verification\n{verify}\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def ingest_lightrag(title: str, content: str) -> tuple[bool, str]:
    payload = json.dumps({"text": content, "description": title}).encode("utf-8")
    req = urllib.request.Request(
        LIGHTRAG_INGEST,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bug closeout autopipeline")
    parser.add_argument("--topic", required=True, help="kebab-case topic name")
    parser.add_argument("--summary", required=True, help="one-line summary")
    parser.add_argument("--root-cause", required=True, help="root cause")
    parser.add_argument("--fix", required=True, help="fix details")
    parser.add_argument("--verify", required=True, help="verification command or proof")
    parser.add_argument("--skip-kg", action="store_true", help="skip dedup-lightrag dry run")
    args = parser.parse_args()

    print("[bug-closeout] start")

    err_path = write_error_log(args.topic, args.summary, args.root_cause, args.fix, args.verify)
    print(f"[bug-closeout] error-log written: {err_path}")

    truth_path = write_truth_source(args.topic, args.summary, args.root_cause, args.fix, args.verify)
    print(f"[bug-closeout] truth-source written: {truth_path}")

    truth_text = truth_path.read_text(encoding="utf-8")
    ok, detail = ingest_lightrag(f"[bug-fix] {args.topic}", truth_text)
    print(f"[bug-closeout] lightrag ingest: {'ok' if ok else 'warn'} ({detail})")

    code, out, err = run([
        "python3",
        "scripts/milestone-judge.py",
        "--topic",
        args.topic,
        "--description",
        args.summary,
    ])
    print(f"[bug-closeout] milestone-judge exit={code}")
    if out:
        print(out)
    if err:
        print(err)

    code, out, err = run(["python3", "scripts/git-score.py"])
    print(f"[bug-closeout] git-score exit={code}")
    if out:
        print(out)
    if err:
        print(err)

    code, out, err = run(["python3", "scripts/truth-xval.py"])
    print(f"[bug-closeout] truth-xval exit={code}")
    if out:
        print(out)
    if err:
        print(err)

    if not args.skip_kg:
        code, out, err = run(["python3", "scripts/dedup-lightrag.py", "--dry-run"])
        print(f"[bug-closeout] dedup-lightrag --dry-run exit={code}")
        if out:
            print(out)
        if err:
            print(err)

    print("[bug-closeout] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())

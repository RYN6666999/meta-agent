#!/usr/bin/env python3
"""
major_change_guard.py

Auto-guard for major changes to avoid forgetting:
- milestone-judge
- git-score

By default, it triggers only when changed files include:
- law.json
- api/**
- scripts/**
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PREFIXES = ("api/", "scripts/")
PROTECTED_FILES = {"law.json"}


def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def get_changed_files() -> list[str]:
    out, _err = "", ""
    code, out, _err = run(["git", "status", "--porcelain"])
    if code != 0 or not out:
        return []

    files: list[str] = []
    for line in out.splitlines():
        m = re.match(r"^.{2}\s+(.+)$", line)
        if not m:
            continue
        path = m.group(1).strip()
        if " -> " in path:
            path = path.split(" -> ")[-1].strip()
        files.append(path)
    return files


def is_major_change(files: list[str]) -> bool:
    for f in files:
        if f in PROTECTED_FILES:
            return True
        if f.startswith(PROTECTED_PREFIXES):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto guard major changes with milestone-judge + git-score")
    parser.add_argument("--topic", default="major-change-autogit-guard", help="milestone topic")
    parser.add_argument("--description", default="major change guard auto-run", help="milestone description")
    parser.add_argument("--force", action="store_true", help="run even if no protected paths changed")
    parser.add_argument("--dry-run", action="store_true", help="show commands without executing")
    args = parser.parse_args()

    files = get_changed_files()
    major = is_major_change(files)

    print(f"[major-guard] changed_files={len(files)} major_change={major}")
    for p in files[:20]:
        print(f"  - {p}")

    if not files:
        print("[major-guard] no working-tree changes, skip")
        return 0

    if not major and not args.force:
        print("[major-guard] no protected paths changed, skip (use --force to override)")
        return 0

    topic = args.topic
    description = f"{args.description} @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    cmd1 = ["python3", "scripts/milestone-judge.py", "--topic", topic, "--description", description]
    cmd2 = ["python3", "scripts/git-score.py"]

    if args.dry_run:
        print("[major-guard] dry-run commands:")
        print("  ", " ".join(cmd1))
        print("  ", " ".join(cmd2))
        return 0

    failed = False

    code, out, err = run(cmd1)
    print(f"[major-guard] milestone-judge exit={code}")
    if out:
        print(out)
    if err:
        print(err)
    if code != 0:
        failed = True

    code, out, err = run(cmd2)
    print(f"[major-guard] git-score exit={code}")
    if out:
        print(out)
    if err:
        print(err)
    if code != 0:
        failed = True

    if failed:
        print("[major-guard] failed: one or more guard steps returned non-zero")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""一鍵 smoke 驗證：依序執行 health_check / e2e_test / replay_degraded_queue。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / 'scripts'
REPORT_FILE = ROOT_DIR / 'memory' / 'smoke-run-report.json'


def run_step(name: str, script_name: str, timeout_sec: int) -> dict:
    started = time.perf_counter()
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            cwd=str(ROOT_DIR),
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        output = ((result.stdout or '') + '\n' + (result.stderr or '')).strip()
        return {
            'name': name,
            'ok': result.returncode == 0,
            'returncode': result.returncode,
            'elapsed_ms': elapsed_ms,
            'output_preview': output[:600],
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            'name': name,
            'ok': False,
            'returncode': -1,
            'elapsed_ms': elapsed_ms,
            'output_preview': str(exc)[:600],
        }


def main() -> int:
    started_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    steps = [
        run_step('health_check', 'health_check.py', timeout_sec=240),
        run_step('e2e_test', 'e2e_test.py', timeout_sec=300),
        run_step('replay_degraded_queue', 'replay_degraded_queue.py', timeout_sec=180),
    ]

    all_ok = all(step.get('ok') for step in steps)
    report = {
        'ok': all_ok,
        'checked_at': started_at,
        'steps': steps,
    }
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    icon = '✅' if all_ok else '❌'
    print(f'[smoke_run] {icon} overall={all_ok} report={REPORT_FILE}', flush=True)
    for step in steps:
        step_icon = '✅' if step['ok'] else '❌'
        print(
            f"[smoke_run] {step_icon} {step['name']} "
            f"rc={step['returncode']} elapsed_ms={step['elapsed_ms']}",
            flush=True,
        )
    return 0 if all_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
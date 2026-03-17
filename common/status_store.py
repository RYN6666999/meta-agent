from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from common.config import STATUS_FILE
from common.jsonio import load_json, save_json


StatusMutator = Callable[[dict[str, Any]], None]


def load_status() -> dict[str, Any]:
    return load_json(STATUS_FILE, {})


def save_status(data: dict[str, Any]) -> None:
    save_json(STATUS_FILE, data)


def update_status(mutator: StatusMutator) -> dict[str, Any]:
    data = load_status()
    if not isinstance(data, dict):
        data = {}
    mutator(data)
    save_status(data)
    return data


def update_reliability_metrics(
    section: dict[str, Any],
    *,
    ok: bool,
    checked_at: str,
) -> None:
    """Update reliability fields for a check section in system-status.

    Fields maintained:
    - consecutive_failures
    - first_failure_at / last_failure_at
    - last_ok_at
    - last_recovered_at
    - mttr_last_seconds
    """
    previous_ok = section.get('ok')
    prev_failures = section.get('consecutive_failures', 0)
    try:
        prev_failures_int = int(prev_failures)
    except Exception:
        prev_failures_int = 0

    if ok:
        was_failing = previous_ok is False or prev_failures_int > 0
        if was_failing:
            section['last_recovered_at'] = checked_at
            first_failure_at = section.get('first_failure_at')
            if isinstance(first_failure_at, str):
                try:
                    t0 = datetime.strptime(first_failure_at, '%Y-%m-%d %H:%M:%S')
                    t1 = datetime.strptime(checked_at, '%Y-%m-%d %H:%M:%S')
                    section['mttr_last_seconds'] = max(0, int((t1 - t0).total_seconds()))
                except Exception:
                    pass
        section['consecutive_failures'] = 0
        section['last_ok_at'] = checked_at
        section.pop('first_failure_at', None)
        section.pop('last_failure_at', None)
        return

    # not ok
    if previous_ok is False:
        section['consecutive_failures'] = prev_failures_int + 1
    else:
        section['consecutive_failures'] = 1
        section['first_failure_at'] = checked_at
    section['last_failure_at'] = checked_at

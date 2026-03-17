#!/usr/bin/env python3
"""回放降級緩衝佇列：當主要 ingest 恢復後，補寫 memory/degraded-ingest-queue.jsonl。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.status_store import load_status, save_status

BACKEND_FILE = ROOT_DIR / 'memory-mcp' / 'server.py'
QUEUE_FILE = ROOT_DIR / 'memory' / 'degraded-ingest-queue.jsonl'
DEFAULT_CONCURRENCY = 8


def load_backend():
    spec = importlib.util.spec_from_file_location('meta_agent_memory_backend', BACKEND_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load backend from {BACKEND_FILE}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_queue() -> tuple[list[dict], int]:
    if not QUEUE_FILE.exists():
        return [], 0
    items: list[dict] = []
    invalid_lines = 0
    for line in QUEUE_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                items.append(row)
            else:
                invalid_lines += 1
        except Exception:
            invalid_lines += 1
    return items, invalid_lines


def write_queue(items: list[dict]) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = QUEUE_FILE.with_suffix('.jsonl.tmp')
    if not items:
        tmp_file.write_text('', encoding='utf-8')
        tmp_file.replace(QUEUE_FILE)
        return
    payload = '\n'.join(json.dumps(i, ensure_ascii=False) for i in items) + '\n'
    tmp_file.write_text(payload, encoding='utf-8')
    tmp_file.replace(QUEUE_FILE)


def _get_concurrency() -> int:
    raw = os.getenv('META_REPLAY_CONCURRENCY', '').strip()
    if not raw:
        return DEFAULT_CONCURRENCY
    try:
        value = int(raw)
    except Exception:
        return DEFAULT_CONCURRENCY
    return max(1, min(64, value))


def _dedup_rows(rows: list[dict]) -> tuple[list[dict], int]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    duplicates = 0
    for row in rows:
        content = str(row.get('content', '')).strip()
        title = str(row.get('title', 'degraded-replay')).strip() or 'degraded-replay'
        if not content:
            continue
        key = (title, content)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        deduped.append(row)
    return deduped, duplicates


async def _replay_one(backend, row: dict, sem: asyncio.Semaphore) -> tuple[bool, dict | None]:
    async with sem:
        content = str(row.get('content', '')).strip()
        title = str(row.get('title', 'degraded-replay')).strip() or 'degraded-replay'
        if not content:
            return True, None
        try:
            result = await backend.ingest_memory(content, 'verified_truth', title)
            if isinstance(result, str) and result.startswith('✅'):
                return True, None
            failed = dict(row)
            failed['last_replay_result'] = str(result)[:200]
            failed['last_replay_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return False, failed
        except Exception as exc:
            failed = dict(row)
            failed['last_replay_result'] = str(exc)[:200]
            failed['last_replay_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return False, failed


async def replay() -> tuple[int, int, str]:
    started = time.perf_counter()
    rows, invalid_lines = parse_queue()
    total_raw = len(rows)
    rows, duplicates = _dedup_rows(rows)
    total = len(rows)
    if total == 0:
        detail = f'queue empty raw={total_raw} invalid={invalid_lines} duplicates={duplicates}'
        return 0, 0, detail

    backend = load_backend()
    sem = asyncio.Semaphore(_get_concurrency())
    tasks = [_replay_one(backend, row, sem) for row in rows]
    results = await asyncio.gather(*tasks)

    remain: list[dict] = []
    success = 0
    for ok, failed_row in results:
        if ok:
            success += 1
        elif isinstance(failed_row, dict):
            remain.append(failed_row)

    write_queue(remain)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    detail = (
        f'success={success} remain={len(remain)} total={total} '
        f'raw={total_raw} invalid={invalid_lines} duplicates={duplicates} elapsed_ms={elapsed_ms}'
    )
    return success, len(remain), detail


def update_status(success: int, remain: int, detail: str) -> None:
    status = load_status()
    status['degraded_queue'] = {
        'ok': remain == 0,
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'success_count': success,
        'remaining_count': remain,
        'detail': detail,
    }
    save_status(status)


def main() -> int:
    success, remain, detail = asyncio.run(replay())
    update_status(success, remain, detail)
    print(f'[replay_degraded_queue] {detail}', flush=True)
    return 0 if remain == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())

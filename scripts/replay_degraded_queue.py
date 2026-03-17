#!/usr/bin/env python3
"""回放降級緩衝佇列：當主要 ingest 恢復後，補寫 memory/degraded-ingest-queue.jsonl。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.status_store import load_status, save_status

BACKEND_FILE = ROOT_DIR / 'memory-mcp' / 'server.py'
QUEUE_FILE = ROOT_DIR / 'memory' / 'degraded-ingest-queue.jsonl'


def load_backend():
    spec = importlib.util.spec_from_file_location('meta_agent_memory_backend', BACKEND_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load backend from {BACKEND_FILE}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    items: list[dict] = []
    for line in QUEUE_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                items.append(row)
        except Exception:
            continue
    return items


def write_queue(items: list[dict]) -> None:
    if not items:
        QUEUE_FILE.write_text('', encoding='utf-8')
        return
    payload = '\n'.join(json.dumps(i, ensure_ascii=False) for i in items) + '\n'
    QUEUE_FILE.write_text(payload, encoding='utf-8')


async def replay() -> tuple[int, int, str]:
    rows = parse_queue()
    total = len(rows)
    if total == 0:
        return 0, 0, 'queue empty'

    backend = load_backend()
    remain: list[dict] = []
    success = 0

    for row in rows:
        content = str(row.get('content', '')).strip()
        title = str(row.get('title', 'degraded-replay')).strip() or 'degraded-replay'
        if not content:
            continue
        try:
            result = await backend.ingest_memory(content, 'verified_truth', title)
            if isinstance(result, str) and result.startswith('✅'):
                success += 1
            else:
                row['last_replay_result'] = str(result)[:200]
                row['last_replay_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                remain.append(row)
        except Exception as exc:
            row['last_replay_result'] = str(exc)[:200]
            row['last_replay_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            remain.append(row)

    write_queue(remain)
    return success, len(remain), f'success={success} remain={len(remain)} total={total}'


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

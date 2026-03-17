#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path('/Users/ryan/meta-agent')
ENV_FILE = ROOT / '.env'
ERROR_DIR = ROOT / 'error-log'
STATE_FILE = ROOT / 'memory' / 'status' / 'mobile_bridge_watchdog.json'
DEDUP_FILE = Path('/tmp/meta-agent-mobile-incident-last.json')
COOLDOWN_SEC = 30 * 60


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            data[key] = value
    return data


def should_emit(topic: str) -> bool:
    now = int(time.time())
    if not DEDUP_FILE.exists():
        DEDUP_FILE.write_text(json.dumps({topic: now}), encoding='utf-8')
        return True

    try:
        data = json.loads(DEDUP_FILE.read_text(encoding='utf-8'))
    except Exception:
        data = {}

    last = int(data.get(topic, 0))
    if now - last < COOLDOWN_SEC:
        return False

    data[topic] = now
    DEDUP_FILE.write_text(json.dumps(data), encoding='utf-8')
    return True


def append_error_log(topic: str, root_cause: str, solution: str, context: str) -> Path:
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime('%Y-%m-%d')
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    filepath = ERROR_DIR / f'{date}-{topic}.md'

    block = (
        f"\n## {ts}\n"
        f"- root_cause: {root_cause}\n"
        f"- solution: {solution}\n"
        f"- context: {context}\n"
    )

    if not filepath.exists():
        filepath.write_text(f"# {topic} incident log\n" + block, encoding='utf-8')
    else:
        with filepath.open('a', encoding='utf-8') as f:
            f.write(block)
    return filepath


def write_status(topic: str, root_cause: str, solution: str, context: str, logged: bool, ingest_ok: bool) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    payload = {
        'ok': ingest_ok,
        'updated_at': now,
        'topic': topic,
        'root_cause': root_cause,
        'solution': solution,
        'context': context,
        'logged': logged,
        'ingest_ok': ingest_ok,
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def try_ingest_via_api(topic: str, root_cause: str, solution: str, context: str) -> bool:
    env = load_env()
    api_key = env.get('META_AGENT_API_KEY') or env.get('API_KEY') or env.get('N8N_API_KEY', '')
    if not api_key:
        return False

    body = {
        'root_cause': root_cause,
        'solution': solution,
        'topic': topic,
        'context': context,
    }
    req = urllib.request.Request(
        'http://127.0.0.1:9901/api/v1/log-error',
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description='Record mobile bridge incidents with auto-ingest.')
    parser.add_argument('--topic', required=True)
    parser.add_argument('--root-cause', required=True)
    parser.add_argument('--solution', required=True)
    parser.add_argument('--context', default='')
    args = parser.parse_args()

    if not should_emit(args.topic):
        write_status(args.topic, args.root_cause, args.solution, args.context, logged=False, ingest_ok=False)
        return 0

    append_error_log(args.topic, args.root_cause, args.solution, args.context)
    ingest_ok = try_ingest_via_api(args.topic, args.root_cause, args.solution, args.context)
    write_status(args.topic, args.root_cause, args.solution, args.context, logged=True, ingest_ok=ingest_ok)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

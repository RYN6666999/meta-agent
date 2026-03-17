#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path('/Users/ryan/meta-agent')
ENV_FILE = ROOT / '.env'
STATUS_FILE = ROOT / 'memory' / 'status' / 'mobile_bridge_watchdog.json'
PUBLIC_URL_FILE = Path('/tmp/meta-agent-public-url.txt')
TUNNEL_MODE_FILE = Path('/tmp/meta-agent-tunnel-mode.txt')


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            data[k] = v
    data.update(os.environ)
    return data


def check_launchd_jobs() -> tuple[bool, str]:
    cmd = ['launchctl', 'list']
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = result.stdout
    ok = 'com.meta-agent.mobile-bridge' in text and 'com.meta-agent.mobile-watchdog' in text
    return ok, 'bridge/watchdog loaded' if ok else 'launchd jobs missing'


def check_local_api(api_key: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        'http://127.0.0.1:9901/api/v1/telegram/config',
        headers={'Authorization': f'Bearer {api_key}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            body = json.loads(r.read().decode('utf-8'))
        ok = bool(body.get('enabled'))
        return ok, f"enabled={body.get('enabled')}"
    except Exception as exc:
        return False, str(exc)


def check_tunnel_mode(env: dict[str, str]) -> tuple[bool, str]:
    mode = TUNNEL_MODE_FILE.read_text(encoding='utf-8').strip() if TUNNEL_MODE_FILE.exists() else ''
    token_ok = bool(env.get('CLOUDFLARE_TUNNEL_TOKEN'))
    url_ok = bool(env.get('MOBILE_PUBLIC_BASE_URL'))
    if mode == 'named':
        ok = token_ok and url_ok
        return ok, f'named mode=True token={token_ok} fixed_url={url_ok}'
    if mode == 'quick':
        return True, 'quick mode (fallback)'
    return False, f'unknown mode={mode}'


def check_public_url_reachable() -> tuple[bool, str]:
    if not PUBLIC_URL_FILE.exists():
        return False, 'missing /tmp/meta-agent-public-url.txt'
    pub = PUBLIC_URL_FILE.read_text(encoding='utf-8').strip()
    if not pub:
        return False, 'public url empty'

    try:
        req = urllib.request.Request(f'{pub}/api/v1/telegram/config')
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.status
        return code in (200, 401, 403), f'public_code={code} url={pub}'
    except urllib.error.HTTPError as exc:
        return exc.code in (401, 403), f'public_code={exc.code} url={pub}'
    except Exception as exc:
        return False, str(exc)


def check_telegram_webhook(env: dict[str, str]) -> tuple[bool, str]:
    bot = env.get('TELEGRAM_BOT_TOKEN', '').strip()
    secret = env.get('TELEGRAM_WEBHOOK_SECRET', '').strip()
    if not bot or not secret:
        return False, 'missing TELEGRAM_BOT_TOKEN/TELEGRAM_WEBHOOK_SECRET'

    if not PUBLIC_URL_FILE.exists():
        return False, 'public url file missing'

    pub = PUBLIC_URL_FILE.read_text(encoding='utf-8').strip()
    target = f'{pub}/api/v1/telegram/webhook/{secret}'

    try:
        with urllib.request.urlopen(f'https://api.telegram.org/bot{bot}/getWebhookInfo', timeout=10) as r:
            body = json.loads(r.read().decode('utf-8'))
        current = str(body.get('result', {}).get('url', ''))
        if current == target:
            return True, f'webhook current={current}'

        # Fallback transport: long polling bridge on local machine.
        poll = subprocess.run(['pgrep', '-f', 'telegram_poll_bridge.py'], capture_output=True, text=True, check=False)
        poll_ok = poll.returncode == 0 and bool((poll.stdout or '').strip())
        if poll_ok:
            return True, f'polling active current={current}'

        return False, f'current={current}'
    except Exception as exc:
        return False, str(exc)


def check_watchdog_status_fresh() -> tuple[bool, str]:
    if not STATUS_FILE.exists():
        return True, 'no incident status yet (acceptable)'
    try:
        body = json.loads(STATUS_FILE.read_text(encoding='utf-8'))
        updated = str(body.get('updated_at', ''))
        if not updated:
            return False, 'updated_at missing'
        dt = datetime.strptime(updated, '%Y-%m-%d %H:%M:%S')
        age = (datetime.now() - dt).total_seconds()
        ok = age <= 3600
        return ok, f'age_seconds={int(age)} ingest_ok={body.get("ingest_ok")}'
    except Exception as exc:
        return False, str(exc)


def check_runtime_log_sink() -> tuple[bool, str]:
    proc = subprocess.run(
        ['pgrep', '-f', r'uvicorn api.server:app --host 127.0.0.1 --port 9901'],
        capture_output=True,
        text=True,
        check=False,
    )
    pid_lines = (proc.stdout or '').strip().splitlines()
    if not pid_lines:
        return False, 'bridge process missing'

    pid = pid_lines[0].strip()
    sinks = subprocess.run(
        ['lsof', '-p', pid, '-a', '-d', '1,2'],
        capture_output=True,
        text=True,
        check=False,
    )
    text = (sinks.stdout or '').strip()
    if not text:
        return False, f'lsof empty pid={pid}'

    lines = [line for line in text.splitlines() if '/private/tmp/' in line or '/tmp/' in line]
    if not lines:
        return False, f'no tmp log sink pid={pid}'

    sink = lines[-1].split()[-1]
    return True, f'pid={pid} sink={sink}'


def main() -> int:
    env = load_env()
    api_key = env.get('META_AGENT_API_KEY') or env.get('API_KEY') or env.get('N8N_API_KEY', '')

    checks: list[tuple[str, bool, str]] = []
    checks.append(('launchd',) + check_launchd_jobs())
    checks.append(('local_api',) + check_local_api(api_key) if api_key else ('local_api', False, 'missing API key'))
    checks.append(('tunnel_mode',) + check_tunnel_mode(env))
    checks.append(('public_reach',) + check_public_url_reachable())
    checks.append(('telegram_webhook',) + check_telegram_webhook(env))
    checks.append(('runtime_log_sink',) + check_runtime_log_sink())
    checks.append(('watchdog_status',) + check_watchdog_status_fresh())

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)

    print('Mobile Bridge Acceptance')
    print('========================')
    for name, ok, detail in checks:
        icon = 'PASS' if ok else 'FAIL'
        print(f'[{icon}] {name}: {detail}')

    print(f'\nSummary: {passed}/{total} passed')
    return 0 if passed == total else 1


if __name__ == '__main__':
    raise SystemExit(main())

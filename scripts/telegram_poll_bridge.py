#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path('/Users/ryan/meta-agent')
ENV_FILE = ROOT / '.env'
OFFSET_FILE = Path('/tmp/meta-agent-telegram-offset.txt')


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k] = v
    return env


def telegram_api(bot_token: str, method: str, params: dict | None = None) -> dict:
    url = f'https://api.telegram.org/bot{bot_token}/{method}'
    data = None
    if params is not None:
        data = urllib.parse.urlencode(params).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode('utf-8'))


def forward_update(secret: str, update: dict) -> None:
    url = f'http://127.0.0.1:9901/api/v1/telegram/webhook/{secret}'
    req = urllib.request.Request(
        url,
        data=json.dumps(update, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=20):
        return


def main() -> int:
    env = load_env()
    bot = env.get('TELEGRAM_BOT_TOKEN', '').strip()
    secret = env.get('TELEGRAM_WEBHOOK_SECRET', '').strip()
    if not bot or not secret:
        return 1

    offset = 0
    if OFFSET_FILE.exists():
        try:
            offset = int(OFFSET_FILE.read_text(encoding='utf-8').strip() or '0')
        except Exception:
            offset = 0

    while True:
        try:
            payload = telegram_api(bot, 'getUpdates', {'timeout': 25, 'offset': offset})
            updates = payload.get('result', []) if isinstance(payload, dict) else []
            for upd in updates:
                try:
                    forward_update(secret, upd)
                except Exception:
                    pass
                uid = int(upd.get('update_id', 0))
                if uid >= offset:
                    offset = uid + 1
                    OFFSET_FILE.write_text(str(offset), encoding='utf-8')
        except urllib.error.HTTPError as exc:
            # 409 indicates webhook is active; wait and retry.
            if exc.code == 409:
                time.sleep(5)
            else:
                time.sleep(3)
        except Exception:
            time.sleep(3)


if __name__ == '__main__':
    raise SystemExit(main())

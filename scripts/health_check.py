#!/usr/bin/env python3
"""
每日健康檢查：LightRAG + n8n + Groq API Key
異常結果寫入 error-log/ + 附加到 pending-decisions.md 供人類判斷

launchd：每天 08:00 執行
手動：python3 scripts/health_check.py
"""
import json, sys, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path('/Users/ryan/meta-agent')
LOG_DIR = BASE_DIR / 'error-log'

env = {}
with open(BASE_DIR / '.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()

now = datetime.now().strftime('%Y-%m-%d %H:%M')
date = datetime.now().strftime('%Y-%m-%d')


def check_lightrag() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen('http://localhost:9621/health', timeout=5) as r:
            return r.status == 200, f'HTTP {r.status}'
    except Exception as e:
        return False, str(e)


def check_n8n() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen('http://localhost:5678/healthz', timeout=5) as r:
            return r.status == 200, f'HTTP {r.status}'
    except Exception as e:
        return False, str(e)


def check_groq() -> tuple[bool, str]:
    key = env.get('GROQ_API_KEY', '')
    if not key:
        return False, 'GROQ_API_KEY 未設定'
    payload = json.dumps({
        'model': 'llama-3.1-8b-instant',
        'messages': [{'role': 'user', 'content': 'ping'}],
        'max_tokens': 5
    }).encode()
    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=payload,
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, f'HTTP {r.status}'
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}: {e.read().decode()[:100]}'
    except Exception as e:
        return False, str(e)


def main():
    checks = [
        ('LightRAG', check_lightrag),
        ('n8n', check_n8n),
        ('Groq API', check_groq),
    ]

    failures = []
    for name, fn in checks:
        ok, msg = fn()
        status = '✅' if ok else '❌'
        print(f'[health_check] {status} {name}: {msg}', flush=True)
        if not ok:
            failures.append((name, msg))

    if failures:
        log_path = LOG_DIR / f'{date}-health-check.md'
        lines = [f'# 健康檢查失敗 {now}\n']
        for name, msg in failures:
            lines.append(f'- **{name}**: {msg}\n')
        log_path.write_text(''.join(lines))
        print(f'[health_check] 已寫入 {log_path}', flush=True)
        return 1

    print(f'[health_check] 全部正常 {now}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

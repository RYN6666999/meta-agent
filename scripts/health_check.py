#!/usr/bin/env python3
"""
每日健康檢查：LightRAG + n8n + Groq API Key
異常結果寫入 error-log，並把 machine-readable 狀態寫入 system-status.json

launchd：每天 08:00 執行
手動：python3 scripts/health_check.py
"""
import json
import importlib
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.config import BASE_DIR, ENV_FILE, LIGHTRAG_API
from common.lightrag_runtime import ensure_lightrag_service
from common.status_store import load_status, save_status

try:
    httpx = importlib.import_module('httpx')
except Exception:
    httpx = None

LOG_DIR = BASE_DIR / 'error-log'
TRUTH_XVAL_SCRIPT = BASE_DIR / 'scripts' / 'truth-xval.py'
REPLAY_QUEUE_SCRIPT = BASE_DIR / 'scripts' / 'replay_degraded_queue.py'

env = {}
with open(ENV_FILE) as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()

now = datetime.now().strftime('%Y-%m-%d %H:%M')
date = datetime.now().strftime('%Y-%m-%d')
model = 'llama-3.1-8b-instant'


def check_lightrag() -> tuple[bool, str]:
    ensure_lightrag_service()
    endpoints = [
        (f'{LIGHTRAG_API}/health', 5),
        (f'{LIGHTRAG_API}/health', 15),
    ]
    last_err = ''
    for url, timeout_sec in endpoints:
        try:
            with urllib.request.urlopen(url, timeout=timeout_sec) as r:
                if r.status == 200:
                    attempt = f'timeout={timeout_sec}s'
                    return True, f'HTTP {r.status} ({attempt})'
                last_err = f'HTTP {r.status}'
        except Exception as e:
            last_err = str(e)
    return False, last_err


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
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': 'ping'}],
        'max_tokens': 5,
    }
    if httpx is not None:
        try:
            r = httpx.post(
                'https://api.groq.com/openai/v1/chat/completions',
                json=payload,
                headers={'Authorization': f'Bearer {key}'},
                timeout=15,
            )
            if r.status_code == 200:
                return True, 'HTTP 200'
            body = r.text[:160]
            return False, f'HTTP {r.status_code}: {body}'
        except Exception as e:
            return False, str(e)

    # httpx 不可用時，改用 curl（通常可避開 urllib 對 Groq 的誤判）
    try:
        cmd = [
            'curl', '-sS', '-o', '/tmp/groq-health-body.json', '-w', '%{http_code}',
            '-X', 'POST',
            'https://api.groq.com/openai/v1/chat/completions',
            '-H', f'Authorization: Bearer {key}',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(payload),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        code = (result.stdout or '').strip()
        body = ''
        try:
            body = Path('/tmp/groq-health-body.json').read_text(encoding='utf-8')[:160]
        except Exception as e:
            body = f'<body_unavailable: {e}>'
        if code == '200':
            return True, 'HTTP 200'
        return False, f'HTTP {code}: {body}'
    except Exception as e:
        return False, str(e)


def classify_groq(detail: str) -> dict:
    if detail.startswith('HTTP 200'):
        return {
            'transport_ok': True,
            'classification': 'ok',
            'working_key': True,
            'model': model,
            'detail': detail,
        }
    lowered = detail.lower()
    if '403' in detail and '1010' in lowered:
        return {
            'transport_ok': False,
            'classification': 'edge_blocked',
            'working_key': True,
            'model': model,
            'detail': detail,
        }
    if '401' in detail:
        return {
            'transport_ok': False,
            'classification': 'invalid_key',
            'working_key': False,
            'model': model,
            'detail': detail,
        }
    return {
        'transport_ok': False,
        'classification': 'unknown_error',
        'working_key': False,
        'model': model,
        'detail': detail,
    }


def write_health_status(lightrag: tuple[bool, str], n8n: tuple[bool, str], groq: tuple[bool, str]) -> None:
    status = load_status()
    groq_meta = classify_groq(groq[1])
    health_ok = lightrag[0] and n8n[0] and groq_meta['working_key']
    status['health_check'] = {
        'ok': health_ok,
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'services': {
            'lightrag': {'ok': lightrag[0], 'detail': lightrag[1]},
            'n8n': {'ok': n8n[0], 'detail': n8n[1]},
            'groq': groq_meta,
        },
    }
    save_status(status)


def run_auto_recovery(trigger: str, failures: list[tuple[str, str]]) -> None:
    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = load_status()
    recovery = status.get('auto_recovery', {})
    steps = []

    try:
        result = subprocess.run(
            [sys.executable, str(TRUTH_XVAL_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        steps.append({
            'step': 'truth_xval',
            'ok': result.returncode == 0,
            'detail': (result.stdout or result.stderr or '').strip()[:240],
        })
    except Exception as exc:
        steps.append({'step': 'truth_xval', 'ok': False, 'detail': str(exc)[:240]})

    recovery['last_trigger'] = {
        'trigger': trigger,
        'triggered_at': now_ts,
        'failures': [{'service': name, 'detail': msg} for name, msg in failures],
        'steps': steps,
    }
    status['auto_recovery'] = recovery
    save_status(status)


def run_replay_queue() -> None:
    try:
        subprocess.run(
            [sys.executable, str(REPLAY_QUEUE_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception:
        # replay 失敗不阻斷健康檢查主流程
        pass


def main():
    lightrag = check_lightrag()
    n8n = check_n8n()
    groq = check_groq()

    failures = []
    for name, result in [('LightRAG', lightrag), ('n8n', n8n), ('Groq API', groq)]:
        ok, msg = result
        status = '✅' if ok else '❌'
        print(f'[health_check] {status} {name}: {msg}', flush=True)
        if not ok:
            failures.append((name, msg))

    write_health_status(lightrag=lightrag, n8n=n8n, groq=groq)

    if failures:
        run_auto_recovery(trigger='health_check_failure', failures=failures)
        log_path = LOG_DIR / f'{date}-health-check.md'
        lines = [f'# 健康檢查失敗 {now}\n']
        for name, msg in failures:
            lines.append(f'- **{name}**: {msg}\n')
        log_path.write_text(''.join(lines))
        print(f'[health_check] 已寫入 {log_path}', flush=True)
        return 1

    run_replay_queue()
    print(f'[health_check] 全部正常 {now}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

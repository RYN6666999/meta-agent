#!/usr/bin/env python3
"""
重新激活所有 n8n active workflows 的 webhook
用途：n8n Docker 重啟後 webhook 會靜默失效，需重新 deactivate→activate

launchd：開機時延遲執行 (RunAtLoad=true, 等待 n8n 就緒)
手動：python3 scripts/reactivate_webhooks.py
"""
import json, time, sys, urllib.request, urllib.error

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')

BASE = 'http://localhost:5678'


def api(method, path, body=None):
    data = json.dumps(body).encode() if body else b''
    req = urllib.request.Request(
        f'{BASE}{path}', data=data or None,
        headers={'X-N8N-API-KEY': key, 'Content-Type': 'application/json'},
        method=method
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def wait_for_n8n(max_wait=90):
    for _ in range(max_wait):
        try:
            urllib.request.urlopen(f'{BASE}/healthz', timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    print('[reactivate_webhooks] 等待 n8n 就緒...', flush=True)
    if not wait_for_n8n():
        print('[reactivate_webhooks] ❌ n8n 未就緒，放棄', flush=True)
        return 1

    wfs = api('GET', '/api/v1/workflows?limit=20').get('data', [])
    active = [w['id'] for w in wfs if w.get('active')]
    print(f'[reactivate_webhooks] 找到 {len(active)} 個 active workflows', flush=True)

    for wid in active:
        try:
            api('POST', f'/api/v1/workflows/{wid}/deactivate')
            time.sleep(0.3)
            api('POST', f'/api/v1/workflows/{wid}/activate')
            print(f'[reactivate_webhooks] ✅ {wid}', flush=True)
        except Exception as e:
            print(f'[reactivate_webhooks] ❌ {wid}: {e}', flush=True)

    print('[reactivate_webhooks] 完成', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

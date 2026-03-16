#!/usr/bin/env python3
"""重新激活所有 n8n webhook workflows，修復 webhook 未註冊問題"""
import json, urllib.request, time

# 讀取 .env
env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')

def api(method, path, body=None):
    url = f'http://localhost:5678{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data,
        headers={'X-N8N-API-KEY': key, 'Content-Type': 'application/json'},
        method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)

# 取得所有 active workflows
wfs = api('GET', '/api/v1/workflows?limit=20').get('data', [])
active_ids = [w['id'] for w in wfs if w.get('active')]
print(f"找到 {len(active_ids)} 個 active workflows")

for wid in active_ids:
    api('POST', f'/api/v1/workflows/{wid}/deactivate')
    time.sleep(0.3)
    api('POST', f'/api/v1/workflows/{wid}/activate')
    print(f"  ✅ re-registered: {wid}")

print("所有 webhook 重新註冊完成")

# 驗證 memory-extract
import urllib.error
payload = json.dumps({'text': '[端對端測試 2026-03-16] n8n webhook 驗證', 'type': 'verification'}).encode()
req2 = urllib.request.Request('http://localhost:5678/webhook/memory-extract',
    data=payload, headers={'Content-Type': 'application/json'}, method='POST')
try:
    with urllib.request.urlopen(req2, timeout=30) as r:
        body = r.read().decode()
        print(f"\n✅ webhook 端對端測試成功 HTTP {r.status}")
        print(f"回應: {body[:300]}")
except urllib.error.HTTPError as e:
    print(f"\n❌ webhook 測試失敗 HTTP {e.code}: {e.read().decode()[:300]}")

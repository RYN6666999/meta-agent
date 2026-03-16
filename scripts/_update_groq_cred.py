#!/usr/bin/env python3
"""更新 n8n Groq API Key credential"""
import json, urllib.request, urllib.error

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
n8n_key = env.get('N8N_API_KEY', '')
groq_key = env.get('GROQ_API_KEY', '')

def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f'http://localhost:5678{path}',
        data=data,
        headers={'X-N8N-API-KEY': n8n_key, 'Content-Type': 'application/json'},
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise Exception(f'HTTP {e.code}: {e.read().decode()[:300]}')

# 1. 列出所有 credentials
creds = api('GET', '/api/v1/credentials')
print('所有 credentials:')
for c in creds.get('data', []):
    print(f"  id={c['id']} name={c['name']} type={c['type']}")

# 2. 找到 Groq API Key credential
groq_cred = None
for c in creds.get('data', []):
    if 'groq' in c.get('name', '').lower():
        groq_cred = c
        break

if not groq_cred:
    print('\n❌ 未找到 Groq credential，嘗試用 ID pNYJAOUBbpixE5oT')
    cred_id = 'pNYJAOUBbpixE5oT'
else:
    cred_id = groq_cred['id']
    print(f'\n找到 Groq credential: id={cred_id} type={groq_cred["type"]}')

# 3. 更新 credential data (httpHeaderAuth 格式)
update_body = {
    'name': 'Groq API Key',
    'type': 'httpHeaderAuth',
    'data': {
        'name': 'Authorization',
        'value': f'Bearer {groq_key}'
    }
}
try:
    result = api('PATCH', f'/api/v1/credentials/{cred_id}', update_body)
    print(f'✅ Credential 已更新: {result.get("name")} (id={result.get("id")})')
except Exception as e:
    print(f'❌ PATCH 失敗: {e}')
    print('\n嘗試 PUT...')
    try:
        result = api('PUT', f'/api/v1/credentials/{cred_id}', update_body)
        print(f'✅ Credential 已更新 (PUT): {result.get("name")}')
    except Exception as e2:
        print(f'❌ PUT 也失敗: {e2}')

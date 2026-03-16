#!/usr/bin/env python3
"""修復 P1-A workflow 的 Groq URL：從本地代理改為官方 API"""
import json, urllib.request, urllib.error

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')
GROQ_API_KEY = env.get('GROQ_API_KEY', '')

def api_get(path):
    req = urllib.request.Request(
        f'http://localhost:5678{path}',
        headers={'X-N8N-API-KEY': key}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)

def api_put(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f'http://localhost:5678{path}',
        data=data,
        headers={'X-N8N-API-KEY': key, 'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f'PUT error {e.code}: {e.read().decode()[:200]}')
        return None

# 取得 P1-A workflow
wf = api_get('/api/v1/workflows/9ABqAtFoJWHmhkEa')
print(f"Workflow: {wf['name']} (active={wf.get('active')})")

# 找到 Groq 節點並修改 URL
modified = False
for node in wf.get('nodes', []):
    if 'groq' in node.get('name', '').lower() or node.get('id') == 'groq-extract':
        old_url = node['parameters'].get('url', 'N/A')
        print(f"\n找到 Groq 節點: {node['name']}")
        print(f"  舊 URL: {old_url}")
        
        # 只更新 URL，保留其他設定不變
        node['parameters']['url'] = 'https://api.groq.com/openai/v1/chat/completions'
        
        print(f"  新 URL: {node['parameters']['url']}")
        modified = True

if not modified:
    print("❌ 未找到 Groq 節點")
    exit(1)

# 先 deactivate
api2 = urllib.request.Request(
    'http://localhost:5678/api/v1/workflows/9ABqAtFoJWHmhkEa/deactivate',
    data=b'',
    headers={'X-N8N-API-KEY': key, 'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(api2, timeout=10) as r:
    pass
print("\n已 deactivate")

# PUT 更新 workflow — 只傳 API 接受的欄位
update_body = {
    'name': wf['name'],
    'nodes': wf['nodes'],
    'connections': wf['connections'],
    'settings': wf.get('settings', {}),
    'staticData': wf.get('staticData', None),
}
result = api_put('/api/v1/workflows/9ABqAtFoJWHmhkEa', update_body)
if result:
    print("✅ Workflow 已更新")
else:
    print("❌ 更新失敗")
    exit(1)

# 重新 activate
api3 = urllib.request.Request(
    'http://localhost:5678/api/v1/workflows/9ABqAtFoJWHmhkEa/activate',
    data=b'',
    headers={'X-N8N-API-KEY': key, 'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(api3, timeout=10) as r:
    pass
print("✅ 已重新 activate")

print(f"\n修復完成。Groq URL 已改為: https://api.groq.com/openai/v1/chat/completions")
print("注意：需確認 n8n credential 'Groq API Key' 有設好 Authorization Bearer header")

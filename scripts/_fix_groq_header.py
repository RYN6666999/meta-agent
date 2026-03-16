#!/usr/bin/env python3
"""修復 P1-A Groq 節點：直接在 header 加入 Authorization（bypass credential 加密問題）"""
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
        raise Exception(f'HTTP {e.code}: {e.read().decode()[:400]}')

# 取得 workflow
wf = api('GET', '/api/v1/workflows/9ABqAtFoJWHmhkEa')

# 修改 Groq 節點的 headers，直接加入 Authorization
for node in wf.get('nodes', []):
    if node.get('id') == 'groq-extract' or ('groq' in node.get('name', '').lower() and node.get('type') == 'n8n-nodes-base.httpRequest'):
        print(f"修改節點: {node['name']}")
        
        # 確保 URL 正確
        node['parameters']['url'] = 'https://api.groq.com/openai/v1/chat/completions'
        
        # 設定 sendHeaders = true, specifyHeaders = keypair
        node['parameters']['sendHeaders'] = True
        node['parameters']['specifyHeaders'] = 'keypair'
        
        # 找現有 headerParameters
        header_params = node['parameters'].get('headerParameters', {})
        params = header_params.get('parameters', [])
        
        # 移除舊的 Authorization header (如果有)
        params = [p for p in params if p.get('name', '').lower() != 'authorization']
        
        # 加入 Authorization: Bearer <key>
        params.append({
            'name': 'Authorization',
            'value': f'Bearer {groq_key}'
        })
        # 確保 Content-Type 存在
        if not any(p.get('name', '').lower() == 'content-type' for p in params):
            params.append({'name': 'Content-Type', 'value': 'application/json'})
        
        node['parameters']['headerParameters'] = {'parameters': params}
        
        # 移除 authentication（不再需要 credential）
        node['parameters']['authentication'] = 'none'
        
        print(f"  URL: {node['parameters']['url']}")
        print(f"  Headers: {[p['name'] for p in params]}")

# Deactivate 前先 save
api('POST', '/api/v1/workflows/9ABqAtFoJWHmhkEa/deactivate')

update_body = {
    'name': wf['name'],
    'nodes': wf['nodes'],
    'connections': wf['connections'],
    'settings': wf.get('settings', {}),
    'staticData': wf.get('staticData', None),
}
result = api('PUT', '/api/v1/workflows/9ABqAtFoJWHmhkEa', update_body)
print('✅ Workflow 已更新')

api('POST', '/api/v1/workflows/9ABqAtFoJWHmhkEa/activate')
print('✅ 重新 activate 完成')
print('\n現在可以重新執行 e2e 測試')

#!/usr/bin/env python3
"""檢查 Workflow C 的 Groq 節點是否有 Authorization header"""
import json, urllib.request

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')
groq_key = env.get('GROQ_API_KEY', '')

req = urllib.request.Request(
    'http://localhost:5678/api/v1/workflows/3E3yP5pGX1GepMuu',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req, timeout=10) as r:
    wf = json.load(r)

for node in wf.get('nodes', []):
    if node.get('type') == 'n8n-nodes-base.httpRequest' and 'groq' in node.get('name', '').lower():
        print(f"Groq 節點: {node['name']}")
        params = node.get('parameters', {})
        headers = params.get('headerParameters', {}).get('parameters', [])
        print(f"Headers: {headers}")
        cred = node.get('credentials', {})
        print(f"Credentials: {cred}")
        has_auth = any(h.get('name', '').lower() == 'authorization' for h in headers)
        print(f"Has Authorization: {has_auth}")
        
        if not has_auth:
            print("  ⚠️  缺少 Authorization header - 需要修復")

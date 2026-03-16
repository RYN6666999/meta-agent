#!/usr/bin/env python3
"""讀取特定節點的 code"""
import json, urllib.request

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')

req = urllib.request.Request(
    'http://localhost:5678/api/v1/workflows/9ABqAtFoJWHmhkEa',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req, timeout=10) as r:
    d = json.load(r)

# 印出所有 function/code 節點的程式碼
for node in d.get('nodes', []):
    ntype = node.get('type', '')
    if 'function' in ntype.lower() or 'code' in ntype.lower():
        print(f"\n=== 節點: {node['name']} ({ntype}) ===")
        params = node.get('parameters', {})
        code = params.get('functionCode', params.get('jsCode', params.get('code', 'N/A')))
        print(code[:800])

#!/usr/bin/env python3
"""快速掃描所有 workflow 的 httpRequest 節點，找出有問題的 URL"""
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
    'http://localhost:5678/api/v1/workflows?limit=20',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req, timeout=10) as r:
    wfs = json.load(r).get('data', [])

for wf in wfs:
    wf_id = wf['id']
    req2 = urllib.request.Request(
        f'http://localhost:5678/api/v1/workflows/{wf_id}',
        headers={'X-N8N-API-KEY': key}
    )
    with urllib.request.urlopen(req2, timeout=10) as r:
        detail = json.load(r)
    
    print(f"\n{'='*50}")
    print(f"Workflow: {wf['name']} (id={wf_id})")
    for node in detail.get('nodes', []):
        if node.get('type') == 'n8n-nodes-base.httpRequest':
            url = node['parameters'].get('url', 'N/A')
            auth = node['parameters'].get('authentication', 'none')
            print(f"  HTTP node: {node['name']}")
            print(f"    URL: {url}")
            print(f"    auth: {auth}")
            if '192.168' in url or 'localhost' in url or '127.0.0' in url:
                print(f"    ⚠️  本地URL！")

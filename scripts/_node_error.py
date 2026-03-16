#!/usr/bin/env python3
"""查看特定節點的完整錯誤"""
import json, urllib.request, sys

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')

eid = sys.argv[1] if len(sys.argv) > 1 else '155'
node_name = sys.argv[2] if len(sys.argv) > 2 else 'Groq 萃取記憶節點'

req = urllib.request.Request(
    f'http://localhost:5678/api/v1/executions/{eid}?includeData=true',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req, timeout=10) as r:
    detail = json.load(r)

rtn = detail.get('data', {}).get('resultData', {}).get('runData', {})
for name, runs in rtn.items():
    if node_name.lower() in name.lower():
        print(f'=== {name} ===')
        for run in runs:
            err = run.get('error')
            if err:
                print('ERROR:')
                print(json.dumps(err, indent=2, ensure_ascii=False))
            else:
                out = run.get('data', {}).get('main', [[]])[0]
                first = out[0].get('json', {}) if out else {}
                print('OUTPUT:', json.dumps(first, indent=2, ensure_ascii=False)[:800])

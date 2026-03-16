#!/usr/bin/env python3
"""完整 dump 執行詳情"""
import json, urllib.request, sys

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')

eid = sys.argv[1] if len(sys.argv) > 1 else '153'
req = urllib.request.Request(
    f'http://localhost:5678/api/v1/executions/{eid}?includeData=true',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req, timeout=10) as r:
    detail = json.load(r)

# 印出完整結構（排除 binary data）
def safe_dump(obj, max_len=300):
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(s) > max_len:
        return s[:max_len] + '...'
    return s

print('Keys:', list(detail.keys()))
print('status:', detail.get('status'))
print('finished:', detail.get('finished'))
print('mode:', detail.get('mode'))

data = detail.get('data') or {}
print('\ndata keys:', list(data.keys()) if isinstance(data, dict) else type(data))

if isinstance(data, dict):
    rd = data.get('resultData', {})
    print('resultData keys:', list(rd.keys()))
    
    err = rd.get('error')
    if err:
        print('\nERROR:', safe_dump(err, 600))
    
    rtn = rd.get('runData', {})
    print(f'\nrunData nodes ({len(rtn)}):')
    for name, runs in rtn.items():
        print(f'  {name}: {len(runs)} run(s)')
        if runs:
            r0 = runs[0]
            print(f'    keys: {list(r0.keys())}')
            if r0.get('error'):
                print(f'    ERROR: {safe_dump(r0["error"], 400)}')

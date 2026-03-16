#!/usr/bin/env python3
"""檢查 n8n 最近執行狀態"""
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
    'http://localhost:5678/api/v1/executions?workflowId=9ABqAtFoJWHmhkEa&limit=3',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req, timeout=10) as r:
    d = json.load(r)

execs = d.get('data', [])
print(f'最近 {len(execs)} 次執行：')
for e in execs:
    print(f"  id={e['id']} status={e['status']} finished={e['finished']}")

if not execs:
    print('無執行記錄')
    exit(0)

# 最新執行詳情
eid = execs[0]['id']
req2 = urllib.request.Request(
    f'http://localhost:5678/api/v1/executions/{eid}',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req2, timeout=10) as r:
    detail = json.load(r)

print()
data = detail.get('data', {})
result = data.get('resultData', {})
rtn = result.get('runData', {})
err = result.get('error', None)
if err:
    print(f'❌ 執行錯誤: {json.dumps(err, ensure_ascii=False)[:300]}')

for node_name, node_runs in rtn.items():
    run = node_runs[0] if node_runs else {}
    err_node = run.get('error')
    if err_node:
        print(f'  ❌ [{node_name}] error: {json.dumps(err_node, ensure_ascii=False)[:200]}')
    else:
        out = run.get('data', {}).get('main', [[]])[0]
        first = out[0].get('json', {}) if out else {}
        print(f'  ✅ [{node_name}] output: {json.dumps(first, ensure_ascii=False)[:150]}')

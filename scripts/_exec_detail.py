#!/usr/bin/env python3
"""查看執行錯誤詳情"""
import json, urllib.request, sys

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')

# 取得最新執行 ID
eid = sys.argv[1] if len(sys.argv) > 1 else '153'

req = urllib.request.Request(
    f'http://localhost:5678/api/v1/executions/{eid}',
    headers={'X-N8N-API-KEY': key}
)
with urllib.request.urlopen(req, timeout=10) as r:
    detail = json.load(r)

data = detail.get('data', {})
result = data.get('resultData', {})
rtn = result.get('runData', {})
err = result.get('error', None)

print(f'=== Execution {eid} ===')
print(f'status: {detail.get("status")}')
print(f'mode: {detail.get("mode")}')
print()

if err:
    print(f'TOP-LEVEL ERROR: {json.dumps(err, indent=2, ensure_ascii=False)[:500]}')
    print()

for node_name, node_runs in rtn.items():
    run = node_runs[0] if node_runs else {}
    err_node = run.get('error')
    if err_node:
        print(f'❌ [{node_name}]')
        print(f'   {json.dumps(err_node, indent=2, ensure_ascii=False)[:400]}')
        print()
    else:
        out = run.get('data', {}).get('main', [[]])[0]
        first = out[0].get('json', {}) if out else {}
        print(f'✅ [{node_name}] => {json.dumps(first, ensure_ascii=False)[:150]}')

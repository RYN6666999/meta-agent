#!/usr/bin/env python3
"""
n8n 執行偵錯工具

用法：
  python n8n_exec_debug.py list [workflowId]   # 最近執行列表（預設 P1-A）
  python n8n_exec_debug.py detail <execId>      # 各節點輸出/錯誤摘要
  python n8n_exec_debug.py dump <execId>        # 原始結構完整 dump
  python n8n_exec_debug.py node <execId> <key>  # 指定節點關鍵字完整錯誤
"""
import json, sys, urllib.request, urllib.error

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
key = env.get('N8N_API_KEY', '')

P1A_WF = '9ABqAtFoJWHmhkEa'


def api(path):
    req = urllib.request.Request(f'http://localhost:5678{path}',
                                 headers={'X-N8N-API-KEY': key})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def cmd_list(wf_id=P1A_WF):
    data = api(f'/api/v1/executions?workflowId={wf_id}&limit=5').get('data', [])
    print(f'最近 {len(data)} 次執行（workflow={wf_id}）：')
    for e in data:
        print(f"  id={e['id']}  status={e['status']}  finished={e['finished']}  {e.get('startedAt','')[:19]}")
    if data:
        print(f'\n最新執行節點狀態：')
        cmd_detail(data[0]['id'])


def cmd_detail(exec_id):
    d = api(f'/api/v1/executions/{exec_id}')
    rtn = d.get('data', {}).get('resultData', {}).get('runData', {})
    err = d.get('data', {}).get('resultData', {}).get('error')
    if err:
        print(f'❌ TOP ERROR: {json.dumps(err, ensure_ascii=False)[:200]}')
    for name, runs in rtn.items():
        run = runs[0] if runs else {}
        node_err = run.get('error')
        if node_err:
            print(f'  ❌ [{name}] {json.dumps(node_err, ensure_ascii=False)[:150]}')
        else:
            out = run.get('data', {}).get('main', [[]])[0]
            first = out[0].get('json', {}) if out else {}
            print(f'  ✅ [{name}] {json.dumps(first, ensure_ascii=False)[:100]}')


def cmd_dump(exec_id):
    d = api(f'/api/v1/executions/{exec_id}')
    print(f'status={d.get("status")}  finished={d.get("finished")}  mode={d.get("mode")}')
    rd = d.get('data', {}).get('resultData', {})
    err = rd.get('error')
    if err:
        print(f'\nERROR: {json.dumps(err, indent=2, ensure_ascii=False)[:600]}')
    rtn = rd.get('runData', {})
    print(f'\nrunData nodes ({len(rtn)}):')
    for name, runs in rtn.items():
        r0 = runs[0] if runs else {}
        if r0.get('error'):
            print(f'  ❌ {name}: {json.dumps(r0["error"], ensure_ascii=False)[:300]}')
        else:
            print(f'  ✅ {name}')


def cmd_node(exec_id, keyword):
    d = api(f'/api/v1/executions/{exec_id}')
    rtn = d.get('data', {}).get('resultData', {}).get('runData', {})
    for name, runs in rtn.items():
        if keyword.lower() in name.lower():
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


if __name__ == '__main__':
    args = sys.argv[1:]
    cmd = args[0] if args else 'list'

    if cmd == 'list':
        cmd_list(args[1] if len(args) > 1 else P1A_WF)
    elif cmd == 'detail' and len(args) > 1:
        cmd_detail(args[1])
    elif cmd == 'dump' and len(args) > 1:
        cmd_dump(args[1])
    elif cmd == 'node' and len(args) > 2:
        cmd_node(args[1], args[2])
    else:
        print(__doc__)

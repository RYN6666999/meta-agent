#!/usr/bin/env python3
"""
n8n Workflow 靜態檢查工具

用法：
  python n8n_workflow_inspect.py scan         # 掃全部 workflow 的 httpRequest URL，標記本地URL
  python n8n_workflow_inspect.py code [wfId]  # 印出 workflow 所有 code/function 節點原始碼
"""
import json, sys, urllib.request

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


def cmd_scan():
    wfs = api('/api/v1/workflows?limit=20').get('data', [])
    for wf in wfs:
        detail = api(f'/api/v1/workflows/{wf["id"]}')
        http_nodes = [n for n in detail.get('nodes', [])
                      if n.get('type') == 'n8n-nodes-base.httpRequest']
        if not http_nodes:
            continue
        print(f"\n{'='*50}")
        print(f"{'✅' if wf.get('active') else '❌'} {wf['name']}")
        for node in http_nodes:
            url = node['parameters'].get('url', 'N/A')
            flag = '  ⚠️  本地URL' if any(x in url for x in ['192.168', 'localhost', '127.0.0']) else ''
            print(f"  {node['name']}: {url}{flag}")


def cmd_code(wf_id=P1A_WF):
    detail = api(f'/api/v1/workflows/{wf_id}')
    print(f"Workflow: {detail['name']}")
    for node in detail.get('nodes', []):
        ntype = node.get('type', '')
        if 'function' in ntype.lower() or 'code' in ntype.lower():
            params = node.get('parameters', {})
            code = params.get('functionCode', params.get('jsCode', params.get('code', '')))
            if code:
                print(f"\n--- {node['name']} ({ntype}) ---")
                print(code[:1000])


if __name__ == '__main__':
    args = sys.argv[1:]
    cmd = args[0] if args else 'scan'

    if cmd == 'scan':
        cmd_scan()
    elif cmd == 'code':
        cmd_code(args[1] if len(args) > 1 else P1A_WF)
    else:
        print(__doc__)

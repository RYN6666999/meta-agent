#!/usr/bin/env python3
"""端對端完整測試：送長文本到 memory webhook"""
import json, urllib.request, urllib.error, time

url = 'http://localhost:5678/webhook/9ABqAtFoJWHmhkEa/webhook/memory-extract'

test_text = """
[端對端測試 2026-03-16 完整流程驗證]

本次驗證 meta-agent 完整記憶萃取流程：
1. n8n webhook 接收對話文本（P1-A workflow）
2. Groq llama-3.1-8b-instant 進行記憶萃取與結構化
3. LightRAG API 接收 ingest 請求，更新知識圖譜

技術棧確認：
- n8n (Docker port 5678) 正常運行
- LightRAG (port 9621) 健康狀態良好
- webhook draft URL 格式: /webhook/{workflowId}/webhook/{path}
- Groq API 用於低成本萃取

此次測試由 GitHub Copilot 自動觸發，作為系統健康驗證。
如果此筆記出現在 LightRAG 圖譜中，代表端對端流程成功。
"""

payload = json.dumps({'conversation': test_text.strip(), 'session_id': 'e2e-test-2026-03-16'}).encode('utf-8')
req = urllib.request.Request(url, data=payload,
    headers={'Content-Type': 'application/json'}, method='POST')

print(f'發送請求... ({len(test_text)} 字)')
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read().decode()
        print(f'HTTP {r.status}')
        try:
            d = json.loads(body)
            print(json.dumps(d, indent=2, ensure_ascii=False))
        except:
            print(f'response: {body[:500]}')
except urllib.error.HTTPError as e:
    print(f'HTTP Error {e.code}: {e.read().decode()[:500]}')
except Exception as e:
    print(f'Error: {e}')

#!/usr/bin/env python3
"""驗證 Groq API Key 並直接測試"""
import json, urllib.request, urllib.error

env = {}
with open('/Users/ryan/meta-agent/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()

groq_key = env.get('GROQ_API_KEY', '')
groq_key_2 = env.get('GROQ_API_KEY_2', '')
print(f'GROQ_API_KEY: {groq_key[:8]}...{groq_key[-4:]} (len={len(groq_key)})')
print(f'GROQ_API_KEY_2: {groq_key_2[:8]}...{groq_key_2[-4:]} (len={len(groq_key_2)})')

payload = json.dumps({
    'model': 'llama-3.1-8b-instant',
    'messages': [{'role': 'user', 'content': 'Say "ok"'}],
    'max_tokens': 5
}).encode()

for name, key in [('PRIMARY', groq_key), ('SECONDARY', groq_key_2)]:
    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
            content = d['choices'][0]['message']['content']
            print(f'✅ {name} KEY 有效! 回應: {content}')
            break
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'❌ {name} KEY HTTP {e.code}: {body[:150]}')
    except Exception as e:
        print(f'💥 {name} KEY Error: {e}')

#!/usr/bin/env python3
"""Local memory extraction pipeline.

Reads conversation text from stdin or --conversation, asks Groq to extract memories,
then ingests them through memory-mcp using the configured LightRAG backend.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.lightrag_runtime import ensure_lightrag_service

BACKEND_FILE = ROOT_DIR / 'memory-mcp' / 'server.py'
ENV_FILE = ROOT_DIR / '.env'
MODEL = 'llama-3.1-8b-instant'

PROMPT = '''你是記憶萃取器。請從對話中提取 3 到 5 條值得長期保存的記憶。
輸出必須是 JSON，格式：
{"memories":[{"title":"...","content":"...","mem_type":"verified_truth"}]}
規則：
- title 8~30 字，具體可讀
- content 60~220 字
- mem_type 只能是 verified_truth、error_fix、tech_decision、rule 其中之一
- 不要輸出 markdown，不要解釋
'''


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        values[k.strip()] = v.strip()
    return values


def load_backend():
    spec = importlib.util.spec_from_file_location('meta_agent_memory_backend', BACKEND_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load backend from {BACKEND_FILE}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_groq(conversation: str) -> list[dict]:
    env = load_env()
    key = env.get('GROQ_API_KEY') or env.get('GROQ_API_KEY_2')
    if not key:
        raise RuntimeError('GROQ_API_KEY not configured')

    payload = json.dumps({
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': PROMPT},
            {'role': 'user', 'content': conversation[:6000]},
        ],
        'temperature': 0.2,
        'max_tokens': 900,
        'response_format': {'type': 'json_object'},
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    content = data['choices'][0]['message']['content']
    parsed = json.loads(content)
    memories = parsed.get('memories', [])
    if not isinstance(memories, list):
        raise RuntimeError('invalid memories payload')
    return [m for m in memories if isinstance(m, dict)]


def heuristic_memories(conversation: str) -> list[dict]:
    cleaned = re.sub(r'\s+', ' ', conversation).strip()
    snippet = cleaned[:220]
    return [
        {
            'title': '對話重點摘要',
            'content': snippet,
            'mem_type': 'verified_truth',
        }
    ]


async def ingest_memories(memories: list[dict]) -> dict:
    ensure_lightrag_service()
    backend = load_backend()
    ingested = 0
    titles: list[str] = []
    skipped = 0
    errors: list[str] = []

    for memory in memories[:5]:
        title = str(memory.get('title', '')).strip()[:80] or 'untitled'
        content = str(memory.get('content', '')).strip()
        mem_type = str(memory.get('mem_type', 'verified_truth')).strip() or 'verified_truth'
        if len(content) < 50:
            skipped += 1
            continue
        result = await backend.ingest_memory(f'[CONFIRMED]\n{content}', mem_type, title)
        if isinstance(result, str) and result.startswith('✅'):
            ingested += 1
            titles.append(title)
        else:
            errors.append(str(result)[:160])

    return {
        'success': ingested > 0 and not errors,
        'summary': f'✅ Ingest {ingested} 條記憶 | ⚠️ 跳過 {skipped} | ❌ 錯誤 {len(errors)}',
        'ingested_count': ingested,
        'memories_titles': titles,
        'errors': errors,
        'timestamp': datetime.now().isoformat(),
    }


def read_conversation(args: argparse.Namespace) -> str:
    if args.conversation:
        return args.conversation
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--conversation', default='')
    parser.add_argument('--session-id', default='')
    args = parser.parse_args()

    conversation = read_conversation(args).strip()
    if len(conversation) < 80:
        print(json.dumps({'success': False, 'summary': '內容太短', 'ingested_count': 0, 'memories_titles': []}, ensure_ascii=False))
        return 1

    try:
        memories = call_groq(conversation)
    except Exception:
        memories = heuristic_memories(conversation)

    result = asyncio.run(ingest_memories(memories))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    raise SystemExit(main())

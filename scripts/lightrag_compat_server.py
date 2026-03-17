#!/usr/bin/env python3
"""LightRAG compatibility server for local recovery mode.

Provides a minimal subset of the LightRAG HTTP API used by this repo:
- GET /health
- POST /documents/text
- POST /query
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
STORE_FILE = ROOT_DIR / 'memory' / 'lightrag-compat-store.jsonl'
HOST = '127.0.0.1'
PORT = 9631


def load_docs() -> list[dict]:
    if not STORE_FILE.exists():
        return []
    docs: list[dict] = []
    for line in STORE_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                docs.append(row)
        except Exception:
            continue
    return docs


def append_doc(doc: dict) -> None:
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STORE_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(doc, ensure_ascii=False) + '\n')


def query_docs(query: str, top_k: int) -> tuple[str, list[dict]]:
    keywords = [kw.lower() for kw in re.split(r'[\s，。？！、]+', query) if len(kw) >= 2]
    if not keywords:
        return '(no query keywords)', []

    scored = []
    for doc in load_docs():
        text = str(doc.get('text', ''))
        lowered = text.lower()
        score = sum(lowered.count(kw) for kw in keywords)
        if score <= 0:
            continue
        title = str(doc.get('description') or doc.get('title') or 'untitled')
        snippet = text[:220].replace('\n', ' ')
        scored.append({'title': title, 'score': score, 'snippet': snippet})

    scored.sort(key=lambda item: item['score'], reverse=True)
    top = scored[: max(top_k, 1)]
    if not top:
        return 'no relevant memory found', []

    lines = []
    for idx, item in enumerate(top, start=1):
        lines.append(f"{idx}. {item['title']} | score={item['score']} | {item['snippet']}")
    return '\n'.join(lines), top


class Handler(BaseHTTPRequestHandler):
    server_version = 'LightRAGCompat/0.1'

    def _read_json(self) -> dict:
        length = int(self.headers.get('Content-Length', '0') or '0')
        raw = self.rfile.read(length) if length > 0 else b'{}'
        try:
            data = json.loads(raw.decode('utf-8'))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._send_json(200, {'status': 'ok', 'mode': 'compat', 'checked_at': datetime.now().isoformat()})
            return
        self._send_json(404, {'error': 'not_found'})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == '/documents/text':
            data = self._read_json()
            text = str(data.get('text', '')).strip()
            description = str(data.get('description', '')).strip() or 'untitled'
            if len(text) < 10:
                self._send_json(400, {'error': 'text_too_short'})
                return
            doc = {
                'description': description,
                'text': text,
                'stored_at': datetime.now().isoformat(),
            }
            append_doc(doc)
            self._send_json(200, {'status': 'stored', 'description': description})
            return
        if parsed.path == '/query':
            data = self._read_json()
            query = str(data.get('query', '')).strip()
            top_k = int(data.get('top_k', 3) or 3)
            response, sources = query_docs(query, top_k=top_k)
            self._send_json(200, {'response': response, 'sources': sources})
            return
        self._send_json(404, {'error': 'not_found'})

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == '__main__':
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'[lightrag_compat] listening on http://{HOST}:{PORT}', flush=True)
    server.serve_forever()

#!/usr/bin/env python3
"""端對端完整測試：送長文本到本地記憶萃取主流程，成功時回寫 system-status。"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.status_store import load_status, save_status

LOCAL_EXTRACT_SCRIPT = ROOT_DIR / 'scripts' / 'local_memory_extract.py'


def update_e2e_status(
    ok: bool,
    detail: str,
    response: dict | None = None,
) -> None:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = load_status()
    titles = []
    if isinstance(response, dict):
        raw_titles = response.get('memories_titles', [])
        if isinstance(raw_titles, list):
            titles = raw_titles
    titles_total = len(titles)
    titles_valid = sum(1 for t in titles if isinstance(t, str) and t.strip() and t.strip() != '?')
    titles_invalid = titles_total - titles_valid
    quality_ok = titles_total > 0 and titles_invalid == 0

    status['e2e_memory_extract'] = {
        'ok': ok and quality_ok,
        'checked_at': now,
        'detail': detail if quality_ok else f'{detail} | title_quality_failed',
        'quality_ok': quality_ok,
        'titles_total': titles_total,
        'titles_valid': titles_valid,
        'titles_invalid': titles_invalid,
        'quality_failure_count': titles_invalid,
        'fallback_used': False,
        'fallback_ok': False,
    }
    if response is not None:
        status['e2e_memory_extract']['response'] = response
    save_status(status)


def main() -> int:
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
""".strip()

    print(f'發送請求... ({len(test_text)} 字)')
    try:
        result = subprocess.run(
            [sys.executable, str(LOCAL_EXTRACT_SCRIPT), '--session-id', 'e2e-test-2026-03-16'],
            input=test_text,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        stdout = (result.stdout or '').strip()
        if stdout:
            print(stdout[:1000])
        data = json.loads(stdout) if stdout else None
        ok = result.returncode == 0
        detail = 'local-memory-extract' if ok else f'local-memory-extract rc={result.returncode}'
        update_e2e_status(ok=ok, detail=detail, response=data)
        final_ok = False
        if isinstance(data, dict):
            titles = data.get('memories_titles', [])
            if isinstance(titles, list) and titles:
                final_ok = all(isinstance(t, str) and t.strip() and t.strip() != '?' for t in titles)
        return 0 if ok and final_ok else 1
    except Exception as e:
        print(f'Error: {e}')
        detail = str(e)
        update_e2e_status(ok=False, detail=detail)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

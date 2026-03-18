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

from common.status_store import load_status, save_status, update_reliability_metrics
from common.code_intelligence import build_failure_enrichment, serialize_code_intel_result

LOCAL_EXTRACT_SCRIPT = ROOT_DIR / 'scripts' / 'local_memory_extract.py'
TRUTH_XVAL_SCRIPT = ROOT_DIR / 'scripts' / 'truth-xval.py'
REACTIVATE_WEBHOOKS_SCRIPT = ROOT_DIR / 'scripts' / 'reactivate_webhooks.py'
DEDUP_LIGHTRAG_SCRIPT = ROOT_DIR / 'scripts' / 'dedup-lightrag.py'


def write_code_intelligence_status(detail: str) -> None:
    result = build_failure_enrichment(
        detail,
        repo='meta-agent',
        target='scripts/e2e_test.py',
        working_dir=ROOT_DIR,
    )
    status = load_status()
    status['code_intelligence'] = {
        **serialize_code_intel_result(result),
        'trigger': 'e2e_failure',
        'source_detail': detail[:500],
    }
    save_status(status)


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

    final_ok = ok and quality_ok
    e2e_section = status.get('e2e_memory_extract', {})
    if not isinstance(e2e_section, dict):
        e2e_section = {}

    e2e_section.update({
        'ok': final_ok,
        'checked_at': now,
        'detail': detail if quality_ok else f'{detail} | title_quality_failed',
        'quality_ok': quality_ok,
        'titles_total': titles_total,
        'titles_valid': titles_valid,
        'titles_invalid': titles_invalid,
        'quality_failure_count': titles_invalid,
        'fallback_used': False,
        'fallback_ok': False,
    })
    if response is not None:
        e2e_section['response'] = response
    update_reliability_metrics(e2e_section, ok=final_ok, checked_at=now)
    status['e2e_memory_extract'] = e2e_section
    save_status(status)


def run_auto_recovery(detail: str) -> None:
    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = load_status()
    recovery = status.get('auto_recovery', {})
    steps = []

    for step_name, script in [
        ('truth_xval', TRUTH_XVAL_SCRIPT),
        ('reactivate_webhooks', REACTIVATE_WEBHOOKS_SCRIPT),
        ('dedup_lightrag_dry_run', DEDUP_LIGHTRAG_SCRIPT),
    ]:
        try:
            cmd = [sys.executable, str(script)]
            if step_name == 'dedup_lightrag_dry_run':
                cmd.append('--dry-run')
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            steps.append({
                'step': step_name,
                'ok': result.returncode == 0,
                'detail': (result.stdout or result.stderr or '').strip()[:240],
            })
        except Exception as exc:
            steps.append({'step': step_name, 'ok': False, 'detail': str(exc)[:240]})

    recovery['last_trigger'] = {
        'trigger': 'e2e_failure',
        'triggered_at': now_ts,
        'failures': [{'service': 'e2e_memory_extract', 'detail': detail}],
        'steps': steps,
    }
    status['auto_recovery'] = recovery
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
        if not (ok and final_ok):
            run_auto_recovery(detail=detail)
            write_code_intelligence_status(detail=detail)
        return 0 if ok and final_ok else 1
    except Exception as e:
        print(f'Error: {e}')
        detail = str(e)
        update_e2e_status(ok=False, detail=detail)
        run_auto_recovery(detail=detail)
        write_code_intelligence_status(detail=detail)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from common.config import STATUS_FILE
from common.jsonio import load_json, save_json


StatusMutator = Callable[[dict[str, Any]], None]

STATUS_SHARD_DIR = STATUS_FILE.parent / 'status'
SHARD_KEYS = {
    'api_health',
    'api_usage',
    'health_check',
    'e2e_memory_extract',
    'code_intelligence',
    'truth_xval',
    'degraded_queue',
    'auto_recovery',
    'obsidian_ingest',
    'persona_tech_radar',
    'tiered_memory',
    'benchmark_baseline',
}


def _shard_path(key: str) -> Path:
    safe = ''.join(ch if (ch.isalnum() or ch in ('_', '-')) else '_' for ch in key)
    return STATUS_SHARD_DIR / f'{safe}.json'


def _summarize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        keys = sorted(payload.keys())[:20]
        return {
            'type': 'dict',
            'keys': keys,
            'key_count': len(payload.keys()),
        }
    if isinstance(payload, list):
        return {
            'type': 'list',
            'length': len(payload),
        }
    text = str(payload)
    return {
        'type': 'scalar',
        'preview': text[:200],
    }


def _compact_status(data: dict[str, Any]) -> dict[str, Any]:
    compact = dict(data)
    api_health = compact.get('api_health')
    if isinstance(api_health, dict):
        api_health = dict(api_health)
        endpoints = api_health.get('endpoints')
        if isinstance(endpoints, dict):
            compact_endpoints: dict[str, Any] = {}
            for name, endpoint_data in endpoints.items():
                if not isinstance(endpoint_data, dict):
                    compact_endpoints[name] = endpoint_data
                    continue
                endpoint = dict(endpoint_data)
                if 'response' in endpoint:
                    endpoint['response_summary'] = _summarize_payload(endpoint['response'])
                    endpoint.pop('response', None)
                if isinstance(endpoint.get('error'), str):
                    endpoint['error'] = endpoint['error'][:240]
                compact_endpoints[name] = endpoint
            api_health['endpoints'] = compact_endpoints
        compact['api_health'] = api_health
    return compact


def load_status() -> dict[str, Any]:
    base = load_json(STATUS_FILE, {})
    if not isinstance(base, dict):
        base = {}
    result = dict(base)
    shard_meta = result.pop('_status_shards', None)

    shard_keys: list[str] = []
    if isinstance(shard_meta, dict) and isinstance(shard_meta.get('keys'), list):
        shard_keys = [str(k) for k in shard_meta.get('keys', [])]
    elif STATUS_SHARD_DIR.exists():
        shard_keys = [p.stem for p in STATUS_SHARD_DIR.glob('*.json')]

    for key in shard_keys:
        shard_data = load_json(_shard_path(key), None)
        if shard_data is not None:
            result[key] = shard_data
    return result


def save_status(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        data = {}

    compact = _compact_status(data)
    STATUS_SHARD_DIR.mkdir(parents=True, exist_ok=True)

    shard_keys = sorted(k for k in compact.keys() if k in SHARD_KEYS)
    for key in shard_keys:
        save_json(_shard_path(key), compact[key])

    # 清理不再使用的舊分片
    expected = {_shard_path(k).name for k in shard_keys}
    for shard_file in STATUS_SHARD_DIR.glob('*.json'):
        if shard_file.name not in expected:
            try:
                shard_file.unlink()
            except Exception:
                pass

    index_data = {k: v for k, v in compact.items() if k not in SHARD_KEYS}
    index_data['_status_shards'] = {
        'version': 1,
        'keys': shard_keys,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    save_json(STATUS_FILE, index_data)


def update_status(mutator: StatusMutator) -> dict[str, Any]:
    data = load_status()
    if not isinstance(data, dict):
        data = {}
    mutator(data)
    save_status(data)
    return data


def update_reliability_metrics(
    section: dict[str, Any],
    *,
    ok: bool,
    checked_at: str,
) -> None:
    """Update reliability fields for a check section in system-status.

    Fields maintained:
    - consecutive_failures
    - first_failure_at / last_failure_at
    - last_ok_at
    - last_recovered_at
    - mttr_last_seconds
    """
    previous_ok = section.get('ok')
    prev_failures = section.get('consecutive_failures', 0)
    try:
        prev_failures_int = int(prev_failures)
    except Exception:
        prev_failures_int = 0

    if ok:
        was_failing = previous_ok is False or prev_failures_int > 0
        if was_failing:
            section['last_recovered_at'] = checked_at
            first_failure_at = section.get('first_failure_at')
            if isinstance(first_failure_at, str):
                try:
                    t0 = datetime.strptime(first_failure_at, '%Y-%m-%d %H:%M:%S')
                    t1 = datetime.strptime(checked_at, '%Y-%m-%d %H:%M:%S')
                    section['mttr_last_seconds'] = max(0, int((t1 - t0).total_seconds()))
                except Exception:
                    pass
        section['consecutive_failures'] = 0
        section['last_ok_at'] = checked_at
        section.pop('first_failure_at', None)
        section.pop('last_failure_at', None)
        return

    # not ok
    if previous_ok is False:
        section['consecutive_failures'] = prev_failures_int + 1
    else:
        section['consecutive_failures'] = 1
        section['first_failure_at'] = checked_at
    section['last_failure_at'] = checked_at

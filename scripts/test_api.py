#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.status_store import load_status, save_status

BASE_DIR = Path("/Users/ryan/meta-agent")
ENV_FILE = BASE_DIR / ".env"


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
    data.update({k: v for k, v in os.environ.items() if k.startswith("META_AGENT") or k.endswith("API_KEY")})
    return data


def summarize_response_payload(payload: object) -> dict[str, object]:
    if isinstance(payload, dict):
        keys = sorted(payload.keys())[:20]
        return {
            "type": "dict",
            "keys": keys,
            "key_count": len(payload.keys()),
        }
    if isinstance(payload, list):
        return {
            "type": "list",
            "length": len(payload),
        }
    text = str(payload)
    return {
        "type": "scalar",
        "preview": text[:200],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for external brain API")
    parser.add_argument("--base-url", default="http://127.0.0.1:9901")
    parser.add_argument("--topic", default="health-title-restored")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("META_AGENT_API_KEY") or env.get("API_KEY") or env.get("N8N_API_KEY")
    if not api_key:
        print("❌ Missing META_AGENT_API_KEY/API_KEY/N8N_API_KEY in .env")
        return 1

    headers = {"Authorization": f"Bearer {api_key}"}
    endpoints = {
        "health": ("GET", "/api/v1/health", None),
        "status": ("GET", "/api/v1/status", None),
        "rules": ("GET", "/api/v1/rules?category=forbidden", None),
        "persona_current": ("GET", "/api/v1/persona/current", None),
        "persona_switch_default": ("POST", "/api/v1/persona/switch", {"persona_id": "default"}),
        "query": ("POST", "/api/v1/query", {"q": args.topic, "mode": "hybrid"}),
        "trace": ("GET", f"/api/v1/trace?topic={args.topic}", None),
        "ingest": (
            "POST",
            "/api/v1/ingest",
            {
                "content": "[CONFIRMED] D4 smoke test memory payload for external brain metadata verification, including enough content to pass validation and remain traceable.",
                "mem_type": "verified_truth",
                "title": "d4-api-ingest-smoke",
                "confidence": 0.91,
                "submitted_by": "scripts/test_api.py",
                "source_session": "d4-smoke",
            },
        ),
        "protocol_parse": (
            "POST",
            "/api/v1/protocol/parse",
            {
                "raw_response": "[GOLEM_MEMORY]Save this as memory[/GOLEM_MEMORY]\n[GOLEM_ACTION]```json\n[{\"action\":\"query_memory\",\"q\":\"health-title-restored\",\"mode\":\"hybrid\"}]\n```[/GOLEM_ACTION]\n[GOLEM_REPLY]Done[/GOLEM_REPLY]"
            },
        ),
        "loop": (
            "POST",
            "/api/v1/loop",
            {
                "user_input": "請查 health",
                "raw_response": "[GOLEM_ACTION]```json\n[{\"action\":\"query_memory\",\"q\":\"health-title-restored\",\"mode\":\"hybrid\"}]\n```[/GOLEM_ACTION]\n[GOLEM_REPLY]我已查詢。[/GOLEM_REPLY]",
                "persist_memory": False,
                "execute_actions": True,
            },
        ),
        "persona_switch": ("POST", "/api/v1/persona/switch", {"persona_id": "builder"}),
    }
    results: dict[str, dict] = {}

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=90) as client:
        for name, (method, path, payload) in endpoints.items():
            start = time.perf_counter()
            try:
                if method == "GET":
                    resp = client.get(path)
                else:
                    resp = client.post(path, json=payload)

                latency_ms = int((time.perf_counter() - start) * 1000)
                item = {
                    "ok": resp.status_code == 200,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                }
                parsed: object
                try:
                    parsed = resp.json()
                except Exception:
                    parsed = resp.text[:300]
                item["response_summary"] = summarize_response_payload(parsed)

                if name == "query" and resp.status_code == 200:
                    qdata = parsed if isinstance(parsed, dict) else {}
                    has_rerank = isinstance(qdata.get("rerank_candidates"), list)
                    has_boost = isinstance(qdata.get("memory_boost_updated"), int)
                    item["ok"] = item["ok"] and has_rerank and has_boost
                if name in ("persona_current", "persona_switch_default", "persona_switch") and resp.status_code == 200:
                    pdata = parsed if isinstance(parsed, dict) else {}
                    has_active = isinstance(pdata.get("active_persona"), str) and len(pdata.get("active_persona", "")) > 0
                    has_list = isinstance(pdata.get("available_personas"), list)
                    item["ok"] = item["ok"] and has_active and has_list

                results[name] = item
                print(f"[{name}] HTTP {resp.status_code} ({latency_ms}ms)")
            except Exception as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                results[name] = {
                    "ok": False,
                    "status_code": 0,
                    "latency_ms": latency_ms,
                    "error": str(exc)[:240],
                }
                print(f"[{name}] ERROR ({latency_ms}ms) {exc}")

    overall_ok = all(item["ok"] for item in results.values())
    status = load_status()
    status["api_health"] = {
        "ok": overall_ok,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": args.base_url,
        "endpoints": results,
        "compact": True,
    }
    save_status(status)

    print(json.dumps(status["api_health"], ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

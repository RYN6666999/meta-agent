#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import httpx

BASE_DIR = Path("/Users/ryan/meta-agent")
ENV_FILE = BASE_DIR / ".env"
STATUS_FILE = BASE_DIR / "memory" / "system-status.json"


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


def load_status() -> dict:
    if not STATUS_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_status(data: dict) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    }
    results: dict[str, dict] = {}

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=90) as client:
        for name, (method, path, payload) in endpoints.items():
            if method == "GET":
                resp = client.get(path)
            else:
                resp = client.post(path, json=payload)
            results[name] = {
                "ok": resp.status_code == 200,
                "status_code": resp.status_code,
            }
            try:
                results[name]["response"] = resp.json()
                if name == "query" and resp.status_code == 200:
                    qdata = results[name]["response"]
                    has_rerank = isinstance(qdata.get("rerank_candidates"), list)
                    has_boost = isinstance(qdata.get("memory_boost_updated"), int)
                    results[name]["ok"] = results[name]["ok"] and has_rerank and has_boost
            except Exception:
                results[name]["response"] = resp.text[:300]
            print(f"[{name}] HTTP {resp.status_code}")

    overall_ok = all(item["ok"] for item in results.values())
    status = load_status()
    status["api_health"] = {
        "ok": overall_ok,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": args.base_url,
        "endpoints": results,
    }
    save_status(status)

    print(json.dumps(status["api_health"], ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

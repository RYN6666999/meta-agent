#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_DIR = Path("/Users/ryan/meta-agent")
ENV_FILE = BASE_DIR / ".env"
STATUS_FILE = BASE_DIR / "memory" / "system-status.json"
REGISTRY_FILE = BASE_DIR / "memory" / "persona-registry.json"
REPORT_ROOT = BASE_DIR / "memory" / "persona-reports"

BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
API_BASE = "http://127.0.0.1:9901"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_persona_id(raw: str) -> str:
    safe = "".join(ch for ch in (raw or "") if ch.isalnum() or ch in "_-").strip("_-")
    return safe[:64] if safe else "builder"


def pick_persona(registry: dict[str, Any], cli_arg: str | None) -> tuple[str, dict[str, Any]]:
    personas = registry.get("personas", {})
    fallback_id = normalize_persona_id(registry.get("active_persona", "builder"))
    persona_id = normalize_persona_id(cli_arg or fallback_id)
    cfg = personas.get(persona_id) or personas.get("builder") or {}
    return persona_id, cfg


def brave_search(api_key: str, query: str, count: int) -> list[dict[str, str]]:
    params = urlencode({"q": query, "count": count})
    data = {}
    for attempt in range(3):
        req = Request(
            f"{BRAVE_API}?{params}",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                break
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    results = data.get("web", {}).get("results", [])
    picked = []
    for item in results[:count]:
        picked.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "description": str(item.get("description", "")).strip(),
                "age": str(item.get("age", "")).strip(),
            }
        )
    return picked


def build_report(persona_id: str, persona_name: str, searches: list[dict[str, Any]]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "---",
        f"date: {datetime.now().strftime('%Y-%m-%d')}",
        "type: verified_truth",
        "status: active",
        f"last_triggered: {datetime.now().strftime('%Y-%m-%d')}",
        "usage_count: 0",
        "confidence: 0.78",
        f"persona_id: {persona_id}",
        "source: persona_tech_radar",
        "---",
        "",
        f"# {persona_name} 技術雷達報告",
        "",
        f"- 生成時間: {now}",
        f"- 人格: {persona_id}",
        "",
        "## 核心觀察",
    ]

    for idx, block in enumerate(searches, start=1):
        lines.append(f"### {idx}. 查詢：{block['query']}")
        if not block["results"]:
            lines.append("- 無結果或請求失敗")
            continue
        first = block["results"][0]
        lines.append(f"- 代表趨勢：{first['title']}")
        if first["description"]:
            lines.append(f"- 摘要：{first['description'][:220]}")
        lines.append("- 來源：")
        for item in block["results"][:3]:
            lines.append(f"  - {item['title']} | {item['url']}")
        lines.append("")

    lines.extend(
        [
            "## 與目前架構的對照建議",
            "- 檢查是否需要更新 FastAPI/slowapi 錯誤保護與 timeout 策略。",
            "- 檢查 MCP 路由與 memory adapter 是否可再抽象化，降低人格擴充成本。",
            "- 每週挑 1 項高影響改動做小型 PoC，再決定是否納入主線。",
            "",
            "## 下次與你討論的議題",
            "- 哪一條技術趨勢最值得在本週投入實作？",
            "- 是否要把此人格的報告同步轉為 business/hr 可讀版本？",
        ]
    )

    return "\n".join(lines) + "\n"


def ingest_report(api_key: str, persona_id: str, content: str, title: str) -> tuple[bool, str]:
    payload = {
        "content": f"[APPROVED] {content}",
        "mem_type": "verified_truth",
        "title": title,
        "confidence": 0.78,
        "submitted_by": "persona_tech_radar",
        "source_session": f"persona-radar-{datetime.now().strftime('%Y%m%d')}",
        "user_id": persona_id,
    }
    req = Request(
        f"{API_BASE}/api/v1/ingest",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok")), str(body.get("message", ""))
    except Exception as e:
        return False, str(e)


def main() -> int:
    env = load_env()
    status = load_json(STATUS_FILE, {})
    registry = load_json(REGISTRY_FILE, {"active_persona": "builder", "personas": {}})

    cli_persona = sys.argv[1] if len(sys.argv) > 1 else None
    persona_id, persona_cfg = pick_persona(registry, cli_persona)
    persona_name = str(persona_cfg.get("name", persona_id))

    radar_cfg = persona_cfg.get("workflow", {}).get("tech_radar", {})
    if not radar_cfg.get("enabled", False):
        status["persona_tech_radar"] = {
            "ok": False,
            "persona_id": persona_id,
            "reason": "workflow disabled",
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_json(STATUS_FILE, status)
        print(f"[persona_tech_radar] skip: {persona_id} disabled")
        return 0

    brave_key = env.get("BRAVE_API_KEY", "")
    if not brave_key:
        status["persona_tech_radar"] = {
            "ok": False,
            "persona_id": persona_id,
            "reason": "BRAVE_API_KEY missing",
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_json(STATUS_FILE, status)
        print("[persona_tech_radar] BRAVE_API_KEY missing")
        return 1

    queries = radar_cfg.get("queries", [])
    max_results = int(radar_cfg.get("max_results_per_query", 5))
    searches = []
    for q in queries:
        try:
            results = brave_search(brave_key, str(q), max_results)
        except Exception as e:
            results = []
            print(f"[persona_tech_radar] query failed: {q} :: {e}")
        searches.append({"query": str(q), "results": results})

    report_text = build_report(persona_id=persona_id, persona_name=persona_name, searches=searches)
    report_dir = REPORT_ROOT / persona_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}-tech-radar.md"
    report_file.write_text(report_text, encoding="utf-8")

    api_key = env.get("META_AGENT_API_KEY") or env.get("API_KEY") or env.get("N8N_API_KEY") or ""
    ingest_ok = False
    ingest_msg = "API key missing"
    if api_key:
        ingest_ok, ingest_msg = ingest_report(
            api_key=api_key,
            persona_id=persona_id,
            content=report_text,
            title=f"{persona_name} 技術雷達 {datetime.now().strftime('%Y-%m-%d')}",
        )

    status["persona_tech_radar"] = {
        "ok": True,
        "persona_id": persona_id,
        "persona_name": persona_name,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "queries": queries,
        "report_file": str(report_file.relative_to(BASE_DIR)),
        "ingest_ok": ingest_ok,
        "ingest_message": ingest_msg,
    }
    save_json(STATUS_FILE, status)

    print(f"[persona_tech_radar] report={report_file}")
    print(f"[persona_tech_radar] ingest_ok={ingest_ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

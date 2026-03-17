#!/usr/bin/env python3
"""
generate-handoff.py — 自動生成交接文件（P0-B）
每天 23:50 執行（launchd），讓下一個 session 無縫接手

修正 v2：即使 master-plan 全部完成，也輸出有用的系統快照
"""

import re
import json
import sys
import subprocess
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

META = Path("/Users/ryan/meta-agent")
if str(META) not in sys.path:
    sys.path.insert(0, str(META))

from common.status_store import load_status

MASTER_PLAN = META / "memory" / "master-plan.md"
HANDOFF_FILE = META / "memory" / "handoff" / "latest-handoff.md"
ERROR_LOG_DIR = META / "error-log"
TURN_COUNT_FILE = META / "memory" / "turn-count.txt"
TODAY = date.today().isoformat()


def get_incomplete_items(text: str) -> list[dict]:
    items, current_section = [], ""
    for line in text.splitlines():
        h3 = re.match(r"^### (.+)", line)
        if h3:
            current_section = h3.group(1).strip()
        todo = re.match(r"^\s*- \[ \] (.+)", line)
        if todo:
            items.append({"section": current_section, "item": todo.group(1).strip()})
    return items


def get_recent_git_log(n: int = 6) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(META), "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip().splitlines()
    except Exception:
        return []


def get_recent_errors() -> list[str]:
    files = sorted(ERROR_LOG_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [f.name for f in files[:5]]


def get_turn_count() -> int:
    try:
        return int(TURN_COUNT_FILE.read_text().strip())
    except Exception:
        return 0


def load_system_status() -> dict:
    status = load_status()
    return status if isinstance(status, dict) else {}


def is_recent_success(event: dict, days: int = 2) -> bool:
    if not event or not event.get("ok"):
        return False
    checked_at = event.get("checked_at", "")
    try:
        dt = datetime.strptime(checked_at, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False
    return (datetime.now() - dt).days <= days


def get_session_number() -> int:
    if HANDOFF_FILE.exists():
        text = HANDOFF_FILE.read_text(encoding="utf-8")
        m = re.search(r"Session (\d+)", text)
        if m:
            return int(m.group(1)) + 1
    return 1


def _is_recent_timestamp(ts: str, minutes: int = 30) -> bool:
    try:
        checked = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False
    return (datetime.now() - checked).total_seconds() <= minutes * 60


def check_services(system_status: dict) -> dict:
    # 優先使用最近一次 health_check 結果，降低瞬時探測誤判。
    health = system_status.get("health_check", {}) if isinstance(system_status, dict) else {}
    checked_at = health.get("checked_at", "") if isinstance(health, dict) else ""
    health_services = health.get("services", {}) if isinstance(health, dict) else {}
    if isinstance(health_services, dict) and _is_recent_timestamp(checked_at, minutes=30):
        mapped = {
            "LightRAG": health_services.get("lightrag", {}),
            "n8n": health_services.get("n8n", {}),
        }
        services: dict[str, str] = {}
        for name, payload in mapped.items():
            ok = isinstance(payload, dict) and payload.get("ok") is True
            services[name] = "✅" if ok else "❌"
        if services:
            return services

    services = {}
    checks = {
        "LightRAG": "http://localhost:9621/health",
        "n8n": "http://localhost:5678/healthz",
    }
    for name, url in checks.items():
        status = "❌"
        for timeout_sec in (2, 5):
            try:
                req = urllib.request.urlopen(url, timeout=timeout_sec)
                status = "✅" if req.status == 200 else "⚠️"
                break
            except urllib.error.HTTPError:
                status = "⚠️"
                break
            except Exception:
                continue
        services[name] = status
    return services


def get_launchd_status() -> list[str]:
    try:
        result = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=3
        )
        lines = []
        for line in result.stdout.splitlines():
            if "meta-agent" in line:
                parts = line.split()
                name = parts[2].split(".")[-1] if len(parts) > 2 else line
                pid = parts[0] if parts[0] != "-" else "idle"
                lines.append(f"{name}({pid})")
        return lines
    except Exception:
        return []


def main():
    session_num = get_session_number()
    master_text = MASTER_PLAN.read_text(encoding="utf-8") if MASTER_PLAN.exists() else ""

    incomplete = get_incomplete_items(master_text)
    git_log = get_recent_git_log()
    recent_errors = get_recent_errors()
    turn_count = get_turn_count()
    system_status = load_system_status()
    services = check_services(system_status)
    launchd = get_launchd_status()
    e2e_event = system_status.get("e2e_memory_extract", {})

    # 未完成項目
    if incomplete:
        pending_lines = []
        for p in ["P0", "P1", "P2", "P3", "P4", "P5"]:
            for item in incomplete:
                if p in item["section"]:
                    pending_lines.append(f"- ⏳ **{item['section']}**：{item['item']}")
        pending_text = "\n".join(pending_lines)
        next_steps = "\n".join(
            f"{i+1}. {item['item']}" for i, item in enumerate(incomplete[:3])
        )
        status_text = "建設中"
    else:
        pending_text = "✅ 所有計劃項目已完成"
        dynamic_steps = []
        if not is_recent_success(e2e_event):
            dynamic_steps.append("驗證各組件端對端功能（n8n webhook → LightRAG ingest）")
        dynamic_steps.append("觀察 launchd 夜間任務結果（memory-decay / generate-handoff）")
        dynamic_steps.append("使用 extract-session.sh 把重要對話 ingest 進 LightRAG")

        if dynamic_steps:
            next_steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(dynamic_steps[:4]))
        else:
            next_steps = "1. 無待辦，維持日常巡檢（health-check + handoff）"
        status_text = "穩定運行"

    service_lines = "\n".join(f"| {k} | {v} |" for k, v in services.items())
    launchd_lines = " | ".join(launchd) if launchd else "（查詢失敗）"
    git_lines = "\n".join(f"- `{line}`" for line in git_log) if git_log else "（無記錄）"
    error_lines = "\n".join(f"- {f}" for f in recent_errors) if recent_errors else "（無）"
    e2e_line = "（無記錄）"
    if e2e_event:
        icon = "✅" if e2e_event.get("ok") else "❌"
        e2e_line = f"{icon} {e2e_event.get('checked_at', '-')}: {e2e_event.get('detail', '-') }"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    handoff = f"""---
date: {TODAY}
session: meta-agent — Session {session_num}
status: {status_text}
generated: {ts}
---

# 最新交接文件

## 系統狀態（{ts} 自動生成）

| 服務 | 狀態 |
|------|------|
{service_lines}

**launchd**：{launchd_lines}
**Turn 計數**：{turn_count}

---

## 未完成項目
{pending_text}

## 下一步（立刻執行）
{next_steps}

---

## 最近 Git 提交
{git_lines}

## 最近 Error Log
{error_lines}

## 最近驗證
- E2E memory-extract：{e2e_line}

---

## 關鍵路徑
| 項目 | 路徑/URL |
|------|---------|
| 工作目錄 | `/Users/ryan/meta-agent/` |
| 法典 | `/Users/ryan/meta-agent/law.json` |
| 完整計劃 | `/Users/ryan/meta-agent/memory/master-plan.md` |
| LightRAG | http://localhost:9621 |
| n8n | http://localhost:5678 |
| memory webhook | http://localhost:5678/webhook/9ABqAtFoJWHmhkEa/webhook/memory-extract |
| extract-session | `bash /Users/ryan/meta-agent/scripts/extract-session.sh '對話內容'` |
"""

    HANDOFF_FILE.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF_FILE.write_text(handoff, encoding="utf-8")
    print(f"[generate-handoff] ✅ 已寫入 {HANDOFF_FILE}")
    print(f"  未完成：{len(incomplete)} | Turn：{turn_count} | 服務：{services}")


if __name__ == "__main__":
    main()

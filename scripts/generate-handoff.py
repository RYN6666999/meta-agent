#!/usr/bin/env python3
"""
generate-handoff.py — 自動生成交接文件（P0-B）
每天 23:50 執行（launchd），讓下一個 session 無縫接手

修正 v2：即使 master-plan 全部完成，也輸出有用的系統快照
"""

import re
import subprocess
import urllib.request
from datetime import date, datetime
from pathlib import Path

META = Path("/Users/ryan/meta-agent")
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


def get_session_number() -> int:
    if HANDOFF_FILE.exists():
        text = HANDOFF_FILE.read_text(encoding="utf-8")
        m = re.search(r"Session (\d+)", text)
        if m:
            return int(m.group(1)) + 1
    return 1


def check_services() -> dict:
    services = {}
    checks = {
        "LightRAG": "http://localhost:9621/health",
        "n8n": "http://localhost:5678/healthz",
    }
    for name, url in checks.items():
        try:
            req = urllib.request.urlopen(url, timeout=2)
            services[name] = "✅" if req.status == 200 else "⚠️"
        except Exception:
            services[name] = "❌"
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
    services = check_services()
    launchd = get_launchd_status()

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
        next_steps = (
            "1. 驗證各組件端對端功能（n8n webhook → LightRAG ingest）\n"
            "2. 觀察 launchd 夜間任務結果（memory-decay / generate-handoff）\n"
            "3. 使用 extract-session.sh 把重要對話 ingest 進 LightRAG\n"
            "4. project-golem 確認 memory-mcp 已加入（.claude/mcp.json 已建立）"
        )
        status_text = "穩定運行"

    service_lines = "\n".join(f"| {k} | {v} |" for k, v in services.items())
    launchd_lines = " | ".join(launchd) if launchd else "（查詢失敗）"
    git_lines = "\n".join(f"- `{line}`" for line in git_log) if git_log else "（無記錄）"
    error_lines = "\n".join(f"- {f}" for f in recent_errors) if recent_errors else "（無）"
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

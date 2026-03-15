#!/usr/bin/env python3
"""
generate-handoff.py — 自動生成交接文件
讀取 master-plan.md 的未完成項目
輸出到 memory/handoff/latest-handoff.md
"""

import re
from datetime import date
from pathlib import Path

MASTER_PLAN = Path("/Users/ryan/meta-agent/memory/master-plan.md")
HANDOFF_FILE = Path("/Users/ryan/meta-agent/memory/handoff/latest-handoff.md")
LAW_JSON = Path("/Users/ryan/meta-agent/law.json")
TODAY = date.today().isoformat()


def extract_incomplete_items(text: str) -> list[dict]:
    """從 master-plan.md 提取未完成項目（- [ ]）"""
    items = []
    current_section = ""
    for line in text.splitlines():
        # 偵測 section 標題
        h3 = re.match(r"^### (.+)", line)
        if h3:
            current_section = h3.group(1).strip()
        # 未完成項目
        todo = re.match(r"^\s*- \[ \] (.+)", line)
        if todo:
            items.append({
                "section": current_section,
                "item": todo.group(1).strip(),
            })
    return items


def extract_completed_items(text: str) -> list[str]:
    """提取已完成項目（- [x] 或 ✅）"""
    items = []
    for line in text.splitlines():
        if re.match(r"^\s*- \[x\] .+", line, re.IGNORECASE):
            items.append(line.strip())
        elif "✅" in line and line.strip().startswith("-"):
            items.append(line.strip())
    return items


def get_session_number() -> int:
    """從現有 handoff 取得 session 號碼"""
    if HANDOFF_FILE.exists():
        text = HANDOFF_FILE.read_text(encoding="utf-8")
        m = re.search(r"Session (\d+)", text)
        if m:
            return int(m.group(1)) + 1
    return 1


def generate_handoff(incomplete: list[dict], completed: list[str]) -> str:
    session_num = get_session_number()

    # 按 section 分組
    sections: dict[str, list[str]] = {}
    for item in incomplete:
        sec = item["section"]
        sections.setdefault(sec, []).append(item["item"])

    # 建立未完成列表（按優先序）
    pending_lines = []
    priority_order = ["P0", "P1", "P2", "P3", "P4", "P5"]
    added = set()

    for p in priority_order:
        for sec, items in sections.items():
            if p in sec and sec not in added:
                added.add(sec)
                for item in items:
                    pending_lines.append(f"- ⏳ **{sec}**：{item}")

    # 其他未分類
    for sec, items in sections.items():
        if sec not in added:
            for item in items:
                pending_lines.append(f"- ⏳ **{sec}**：{item}")

    pending_text = "\n".join(pending_lines) if pending_lines else "（無）"

    # 下一步：取前 3 個未完成
    next_steps = []
    for i, item in enumerate(incomplete[:3], 1):
        next_steps.append(f"{i}. {item['item']}")
    next_steps_text = "\n".join(next_steps) if next_steps else "（全部完成）"

    handoff = f"""---
date: {TODAY}
session: meta-agent 建設階段 — Session {session_num}
status: in_progress
---

# 最新交接文件

## 當前狀態
基礎建設完畢，正在建設自動化層。

## 已完成 ✅
{chr(10).join(completed[-10:]) if completed else "（無）"}

## 未完成（按優先序）
{pending_text}

## 下一步（立刻執行）
{next_steps_text}

## 關鍵路徑
- 完整計劃：`/Users/ryan/meta-agent/memory/master-plan.md`
- 法典：`/Users/ryan/meta-agent/law.json`
- LightRAG WebUI：http://localhost:9621/webui
- n8n：http://localhost:5678
- **Claude Code 工作目錄：`/Users/ryan/meta-agent/`**
"""
    return handoff


def main():
    if not MASTER_PLAN.exists():
        print(f"[generate-handoff] 錯誤：找不到 {MASTER_PLAN}")
        return

    text = MASTER_PLAN.read_text(encoding="utf-8")
    incomplete = extract_incomplete_items(text)
    completed = extract_completed_items(text)

    print(f"[generate-handoff] 找到 {len(incomplete)} 個未完成，{len(completed)} 個已完成")

    handoff_content = generate_handoff(incomplete, completed)

    HANDOFF_FILE.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF_FILE.write_text(handoff_content, encoding="utf-8")

    print(f"[generate-handoff] 已寫入 {HANDOFF_FILE}")
    print(handoff_content)


if __name__ == "__main__":
    main()

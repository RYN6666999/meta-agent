#!/usr/bin/env python3
"""
on-stop.py — Claude Code Stop hook
每次 Claude 回應結束時執行：
1. 計數器 +1，存到 memory/turn-count.txt
2. 每 20 次 → 寫入 checkpoint（讀 master-plan 未完成項目）
3. 每次 → 呼叫 generate-handoff.py 更新 latest-handoff.md（保持中斷恢復最新）

4. 每 50 次 → 自動讀取 ~/.claude/projects/ JSONL，送 n8n 記憶萃取 webhook
此腳本從 stdin 讀取 hook JSON（Claude Code 規範）
"""

import sys
import json
import os
import subprocess
from datetime import datetime, date
from pathlib import Path

META = Path("/Users/ryan/meta-agent")
COUNTER_FILE = META / "memory" / "turn-count.txt"
CHECKPOINT_DIR = META / "memory" / "checkpoints"
WEBHOOK_URL = "http://localhost:5678/webhook/9ABqAtFoJWHmhkEa/webhook/memory-extract"

# 讀取 hook 輸入
try:
    hook_input = json.load(sys.stdin)
except Exception:
    hook_input = {}

session_id = hook_input.get("session_id", "unknown")

# ── 計數器 ──────────────────────────────────────────
COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
try:
    turn = int(COUNTER_FILE.read_text().strip())
except Exception:
    turn = 0
turn += 1
COUNTER_FILE.write_text(str(turn))

# ── 每 20 次寫 checkpoint ──────────────────────────
if turn % 20 == 0:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cp_file = CHECKPOINT_DIR / f"checkpoint-{session_id[:8]}-{ts}.md"

    # 讀取 master-plan 的未完成項目
    master = META / "memory" / "master-plan.md"
    pending = []
    if master.exists():
        for line in master.read_text().splitlines():
            if "- [ ]" in line:
                pending.append(line.strip())

    cp_content = f"""---
date: {date.today()}
session: {session_id}
turn: {turn}
type: checkpoint
---

# Checkpoint（Turn {turn}）

## 時間
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 未完成項目（來自 master-plan）
{chr(10).join(pending[:10]) if pending else '（無）'}

## 注意
此文件由 Stop hook 自動生成。如果對話中斷，下次讀取此文件可恢復進度。
"""
    cp_file.write_text(cp_content)
    sys.stderr.write(f"[checkpoint] Turn {turn} → {cp_file.name}\n")

# ── 每 50 次送 n8n 萃取（需要對話內容，此處跳過自動觸發）──
# ── 每 50 次自動萃取 session JSONL → n8n ──────────────────────────
if turn % 50 == 0:
    try:
        import urllib.request as _urllib_req
        claude_project_dir = Path.home() / ".claude" / "projects" / "-Users-ryan"
        jsonl_file = claude_project_dir / f"{session_id}.jsonl"
        turns_texts = []
        if jsonl_file.exists():
            with open(jsonl_file, encoding="utf-8") as jf:
                for line in jf:
                    try:
                        row = json.loads(line)
                        if row.get("type") not in ("user", "assistant"):
                            continue
                        msg = row.get("message", {})
                        role = msg.get("role", row.get("type", "?"))
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            text = " ".join(
                                c.get("text", "") for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                            )
                        else:
                            text = str(content)
                        if text.strip():
                            turns_texts.append(f"[{role}] {text[:800]}")
                    except Exception:
                        continue
        if len(turns_texts) >= 5:
            excerpt = "\n---\n".join(turns_texts[-30:])
            payload_bytes = json.dumps({
                "conversation": excerpt,
                "session_id": session_id,
                "turn": turn,
                "auto": True,
            }).encode("utf-8")
            req = _urllib_req.Request(
                WEBHOOK_URL,
                data=payload_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _urllib_req.urlopen(req, timeout=30) as resp:
                sys.stderr.write(
                    f"[on-stop] auto-extract sent (turn={turn}, turns={len(turns_texts)}), status={resp.status}\n"
                )
        else:
            sys.stderr.write(f"[on-stop] auto-extract skip: {len(turns_texts)} turns < 5\n")
    except Exception as e:
        sys.stderr.write(f"[on-stop] auto-extract error: {e}\n")

# ── 每次都更新 handoff（確保中斷恢復永遠最新）──────────────
try:
    subprocess.run(
        [sys.executable, str(META / "scripts" / "generate-handoff.py")],
        timeout=30, check=False, capture_output=True
    )
    sys.stderr.write(f"[on-stop] handoff updated (turn {turn})\n")
except Exception as e:
    sys.stderr.write(f"[on-stop] generate-handoff failed: {e}\n")

sys.exit(0)

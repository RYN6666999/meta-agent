#!/usr/bin/env python3
"""
on-stop.py — Claude Code Stop hook
每次 Claude 回應結束時執行：
1. 計數器 +1，存到 memory/turn-count.txt
2. 每 20 次 → 寫入 checkpoint（讀 master-plan 未完成項目）

注意：完整對話萃取需手動呼叫 scripts/extract-session.sh
（Stop hook 無法取得對話文本，n8n P1-A webhook 靠手動觸發）

此腳本從 stdin 讀取 hook JSON（Claude Code 規範）
"""

import sys
import json
import os
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
# 對話文本無法直接從 Stop hook 取得，由使用者手動呼叫
# /Users/ryan/meta-agent/scripts/extract-conversation.sh

sys.exit(0)

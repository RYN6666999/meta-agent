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
import subprocess
from datetime import datetime, date
from pathlib import Path

META = Path("/Users/ryan/meta-agent")
COUNTER_FILE = META / "memory" / "turn-count.txt"
CHECKPOINT_DIR = META / "memory" / "checkpoints"
LOCAL_EXTRACT_SCRIPT = META / "scripts" / "local_memory_extract.py"
STATUS_FILE = META / "memory" / "system-status.json"
RUNTIME_STATE_FILE = META / "memory" / "on-stop-state.json"
HANDOFF_MIN_INTERVAL_SEC = 300
EXTRACT_MIN_INTERVAL_SEC = 300


def load_json_file(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_extract_every_turn() -> int:
    status = load_json_file(STATUS_FILE)
    health_ok = bool(status.get("health_check", {}).get("ok", False))
    e2e_ok = bool(status.get("e2e_memory_extract", {}).get("ok", False))
    if health_ok and e2e_ok:
        return 30
    return 10

# 讀取 hook 輸入
try:
    hook_input = json.load(sys.stdin)
except Exception:
    hook_input = {}

session_id = hook_input.get("session_id", "unknown")
runtime_state = load_json_file(RUNTIME_STATE_FILE)
now_ts = int(datetime.now().timestamp())

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

# ── 每 10 次自動萃取 session JSONL → n8n ──────────────────────────
# Bug 修復：
#   1. 路徑動態搜尋，不再寫死 -Users-ryan（meta-agent 實際在 -Users-ryan-meta-agent）
#   2. assistant content 為 list[{type, text/thinking}]，只取 type==text 區塊
extract_every = get_extract_every_turn()
extract_due = turn % extract_every == 0
last_extract_ts = int(runtime_state.get("last_extract_ts", 0) or 0)
extract_debounced = now_ts - last_extract_ts < EXTRACT_MIN_INTERVAL_SEC
if extract_due and not extract_debounced:
    try:
        # 動態搜尋：掃描所有 project dirs 找符合 session_id 的 JSONL
        claude_projects_root = Path.home() / ".claude" / "projects"
        jsonl_file = None
        for proj_dir in claude_projects_root.iterdir():
            candidate = proj_dir / f"{session_id}.jsonl"
            if candidate.exists():
                jsonl_file = candidate
                break
        turns_texts = []
        if jsonl_file and jsonl_file.exists():
            with open(jsonl_file, encoding="utf-8") as jf:
                for line in jf:
                    try:
                        row = json.loads(line)
                        if row.get("type") not in ("user", "assistant"):
                            continue
                        msg = row.get("message", {})
                        role = msg.get("role", row.get("type", "?"))
                        content = msg.get("content", "")
                        # assistant content 是 [{type: thinking/text, text: ...}]
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
        else:
            sys.stderr.write(f"[on-stop] JSONL not found for session {session_id[:8]}\n")
        if len(turns_texts) >= 3:
            excerpt = "\n---\n".join(turns_texts[-30:])
            result = subprocess.run(
                [sys.executable, str(LOCAL_EXTRACT_SCRIPT), "--session-id", session_id],
                input=excerpt,
                text=True,
                capture_output=True,
                timeout=90,
                check=False,
            )
            sys.stderr.write(
                f"[on-stop] local-extract done (turn={turn}, turns={len(turns_texts)})"
                f" rc={result.returncode} from {jsonl_file.name if jsonl_file else '?'}\n"
            )
            runtime_state["last_extract_ts"] = now_ts
        else:
            sys.stderr.write(f"[on-stop] auto-extract skip: {len(turns_texts)} turns < 3\n")
    except Exception as e:
        sys.stderr.write(f"[on-stop] auto-extract error: {e}\n")
elif extract_due and extract_debounced:
    wait_sec = EXTRACT_MIN_INTERVAL_SEC - (now_ts - last_extract_ts)
    sys.stderr.write(f"[on-stop] auto-extract debounce: wait {wait_sec}s\n")

# ── 每次都更新 handoff（確保中斷恢復永遠最新）──────────────
last_handoff_ts = int(runtime_state.get("last_handoff_ts", 0) or 0)
handoff_debounced = now_ts - last_handoff_ts < HANDOFF_MIN_INTERVAL_SEC
if not handoff_debounced:
    try:
        subprocess.run(
            [sys.executable, str(META / "scripts" / "generate-handoff.py")],
            timeout=30, check=False, capture_output=True
        )
        runtime_state["last_handoff_ts"] = now_ts
        sys.stderr.write(f"[on-stop] handoff updated (turn {turn})\n")
    except Exception as e:
        sys.stderr.write(f"[on-stop] generate-handoff failed: {e}\n")
else:
    wait_sec = HANDOFF_MIN_INTERVAL_SEC - (now_ts - last_handoff_ts)
    sys.stderr.write(f"[on-stop] handoff debounce: wait {wait_sec}s\n")

runtime_state["last_turn"] = turn
runtime_state["last_session_id"] = session_id
save_json_file(RUNTIME_STATE_FILE, runtime_state)

sys.exit(0)

#!/usr/bin/env python3
"""
pre-tool-memory-check.py — PreToolUse hook
Edit/Write 工具執行前，掃描本地 error-log/ 有無相關記憶，輸出到 stderr 提示 Claude。
不呼叫 LightRAG（太慢），改用快速本地關鍵詞掃描。
永遠 exit 0（不阻塞），僅提供情報。
"""

import json
import sys
import os
import re
from pathlib import Path

META = Path("/Users/ryan/meta-agent")
SCAN_DIRS = [META / "error-log", META / "truth-source"]

NOISE_FILES = {
    "git-score-log.md", "milestone-judge-log.md", "turn-count.txt",
    "ingest-tracker.json", "latest-handoff.md",
}


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    filename = os.path.basename(file_path)
    if filename in NOISE_FILES:
        sys.exit(0)

    # 關鍵詞：檔名 + 路徑最後 2 段，拆分單字
    raw = re.split(r"[/\\._\-]", filename.lower()) + \
          re.split(r"[/\\._\-]", os.path.dirname(file_path).lower().split("/")[-1])
    keywords = [kw for kw in raw if len(kw) >= 3][:6]
    if not keywords:
        sys.exit(0)

    matches = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for md_file in sorted(scan_dir.rglob("*.md"), reverse=True)[:50]:
            try:
                text_lower = md_file.read_text(encoding="utf-8").lower()
                hit_count = sum(1 for kw in keywords if kw in text_lower)
                if hit_count >= 2:
                    # 提取第一條非空、非 frontmatter 的內容行
                    lines = [l.strip() for l in md_file.read_text(encoding="utf-8").splitlines()
                             if l.strip() and not l.startswith("---") and not l.startswith("#")]
                    snippet = lines[0][:100] if lines else md_file.name
                    matches.append((hit_count, md_file.name, snippet))
            except Exception:
                continue

    if matches:
        matches.sort(reverse=True)
        hints = "; ".join(f"{name}: {snippet}" for _, name, snippet in matches[:3])
        print(f"[memory-hint] {filename} 相關錯誤記錄：{hints}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()

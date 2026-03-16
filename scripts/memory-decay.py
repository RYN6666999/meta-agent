#!/usr/bin/env python3
"""
memory-decay.py — 遺忘曲線引擎
每天掃描 memory/ 下所有 .md 的 frontmatter
計算衰退分數：score = base_score × (0.9 ^ days_since_triggered)
score < 20 → status 改為 deprecated
"""

import os
import re
import math
from datetime import datetime, date
from pathlib import Path

META_DIR = Path("/Users/ryan/meta-agent")
SCAN_DIRS = [
    META_DIR / "memory",
    META_DIR / "error-log",
    META_DIR / "truth-source",
]
DECAY_LOG = META_DIR / "memory" / "decay-log.md"
TODAY = date.today()
DECAY_RATE = 0.9
DEPRECATE_THRESHOLD = 20
BASE_SCORE = 100


def parse_frontmatter(text: str) -> dict:
    """解析 YAML frontmatter，回傳 dict 和 frontmatter 結束位置"""
    if not text.startswith("---"):
        return {}, 0
    end = text.find("\n---", 3)
    if end == -1:
        return {}, 0
    fm_text = text[3:end].strip()
    result = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result, end + 4  # skip closing ---\n


def update_frontmatter(text: str, updates: dict) -> str:
    """更新 frontmatter 中指定的 key"""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    fm_text = text[3:end].strip()
    lines = fm_text.splitlines()
    updated_keys = set()
    new_lines = []
    for line in lines:
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}: {updates[k]}")
                updated_keys.add(k)
                continue
        new_lines.append(line)
    # 加入不存在的新 key
    for k, v in updates.items():
        if k not in updated_keys:
            new_lines.append(f"{k}: {v}")
    new_fm = "\n".join(new_lines)
    return f"---\n{new_fm}\n---" + text[end + 4:]


def days_since(date_str: str) -> int:
    """計算距今幾天"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return max(0, (TODAY - d).days)
    except (ValueError, TypeError):
        return 0


def compute_score(base: float, days: int) -> float:
    return base * (DECAY_RATE ** days)


def process_file(filepath: Path) -> dict | None:
    """處理單一 .md 檔案，回傳處理結果"""
    text = filepath.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(text)

    if not fm:
        return None

    # 只處理有 type 的記憶檔案
    mem_type = fm.get("type", "")
    if not mem_type:
        return None

    status = fm.get("status", "active")
    if status == "deprecated":
        return None  # 已過期，跳過

    last_triggered = fm.get("last_triggered", fm.get("date", ""))
    days = days_since(last_triggered) if last_triggered else 0
    score = compute_score(BASE_SCORE, days)

    result = {
        "file": str(filepath),
        "type": mem_type,
        "status": status,
        "days_inactive": days,
        "score": round(score, 2),
        "action": "keep",
    }

    if score < DEPRECATE_THRESHOLD:
        updates = {"status": "deprecated"}
        new_text = update_frontmatter(text, updates)
        filepath.write_text(new_text, encoding="utf-8")
        result["action"] = "deprecated"

    return result


def scan_memory_dir() -> list[dict]:
    """掃描 memory/ + error-log/ + truth-source/ 目錄"""
    SKIP_DIRS = {"handoff", "checkpoints", "archive"}
    results = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            if any(skip in md_file.parts for skip in SKIP_DIRS):
                continue
            result = process_file(md_file)
            if result:
                results.append(result)
    return results


def write_decay_log(results: list[dict]):
    """追加寫入衰退日誌"""
    log_path = DECAY_LOG
    deprecated = [r for r in results if r["action"] == "deprecated"]
    kept = [r for r in results if r["action"] == "keep"]

    entry = f"\n## {TODAY} 衰退掃描\n"
    entry += f"- 掃描檔案：{len(results)} 個\n"
    entry += f"- 保留：{len(kept)} 個\n"
    entry += f"- 標記 deprecated：{len(deprecated)} 個\n"

    if deprecated:
        entry += "\n### 已標記 deprecated\n"
        for r in deprecated:
            name = Path(r["file"]).name
            entry += f"- `{name}` (score={r['score']}, 閒置 {r['days_inactive']} 天)\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)

    print(entry)


def main():
    print(f"[memory-decay] {TODAY} 開始掃描 {[str(d) for d in SCAN_DIRS]}")
    results = scan_memory_dir()
    write_decay_log(results)
    deprecated_count = sum(1 for r in results if r["action"] == "deprecated")
    print(f"[memory-decay] 完成。處理 {len(results)} 個，deprecated {deprecated_count} 個")


if __name__ == "__main__":
    main()

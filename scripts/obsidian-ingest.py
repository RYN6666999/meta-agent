#!/usr/bin/env python3
"""
Obsidian → LightRAG 自動同步器 (obsidian-ingest.py)

觸發方式：
  - launchd 每 30 分鐘執行（com.meta-agent.obsidian-ingest）
  - 手動：python3 scripts/obsidian-ingest.py
  - 首次初始化：python3 scripts/obsidian-ingest.py --init（掃全部）
  - 指定目錄：python3 scripts/obsidian-ingest.py --path TikTok_Notes

工作流程：
  1. 讀取 memory/obsidian-sync.json 取得 last_synced 時間戳
  2. 掃描 Obsidian vault 中 mtime > last_synced 的 .md 文件
  3. 過濾：字數 > 200、不在 ignore list、不是模板
  4. POST 到 LightRAG /documents/text
  5. 成功後更新 last_synced
  6. 結果寫入 system-status.json["obsidian_ingest"]
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.config import BASE_DIR, LIGHTRAG_API
from common.jsonio import load_json, save_json

# ── 路徑設定 ─────────────────────────────────────────────────────
OBSIDIAN_VAULT = Path("/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun")
SYNC_STATE = BASE_DIR / "memory" / "obsidian-sync.json"
STATUS_FILE = BASE_DIR / "memory" / "system-status.json"

# ── 跳過清單（系統文件/緩存/不需 ingest 的目錄）────────────────────
IGNORE_DIRS = {".obsidian", ".trash", "Extras", "templates", "Templates"}
IGNORE_FILES = {"douyin-cache.md", "未命名.md"}
MIN_CHARS = 200   # 低於此字數跳過（太短 = 可能是空殼或緩存）
MAX_CHARS = 8000  # 截斷上限（防止 LightRAG token 過載）


# ── 工具函式 ─────────────────────────────────────────────────────

def lightrag_health() -> bool:
    try:
        with urllib.request.urlopen(f"{LIGHTRAG_API}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def lightrag_ingest(title: str, content: str) -> tuple[bool, str]:
    """POST 到 LightRAG /documents/text"""
    payload = json.dumps({
        "text": content[:MAX_CHARS],
        "description": title,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{LIGHTRAG_API}/documents/text",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def scan_vault(since_ts: float, target_path: str | None = None) -> list[Path]:
    """
    掃描 vault 中 mtime > since_ts 的 .md 文件。
    target_path: 若指定，只掃此子目錄（相對 vault 根）。
    """
    base = OBSIDIAN_VAULT
    if target_path:
        base = OBSIDIAN_VAULT / target_path

    results = []
    for md_file in base.rglob("*.md"):
        # 過濾忽略目錄
        parts = set(md_file.relative_to(OBSIDIAN_VAULT).parts)
        if parts & IGNORE_DIRS:
            continue
        # 過濾忽略文件
        if md_file.name in IGNORE_FILES:
            continue
        # 時間過濾（init 模式 since_ts=0 代表全掃）
        if md_file.stat().st_mtime <= since_ts:
            continue
        results.append(md_file)

    return sorted(results, key=lambda f: f.stat().st_mtime, reverse=True)


def build_title(md_file: Path) -> str:
    """從文件路徑構建易讀標題"""
    rel = md_file.relative_to(OBSIDIAN_VAULT)
    parts = list(rel.parts)
    if len(parts) == 1:
        return f"【Obsidian】{parts[0].removesuffix('.md')}"
    return f"【Obsidian/{'/'.join(parts[:-1])}】{parts[-1].removesuffix('.md')}"


# ── 主程式 ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Obsidian vault → LightRAG 自動同步")
    parser.add_argument("--init", action="store_true", help="初始化：掃全部文件（忽略上次同步時間）")
    parser.add_argument("--path", metavar="SUBDIR", help="只同步指定子目錄，例如 TikTok_Notes")
    parser.add_argument("--dry-run", action="store_true", help="只列出要 ingest 的文件，不實際送出")
    args = parser.parse_args()

    now_ts = datetime.now(timezone.utc).timestamp()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"🔄 Obsidian → LightRAG 同步器  {now_str}")
    print("=" * 52)

    # ── 檢查 LightRAG ──
    if not lightrag_health():
        print("❌ LightRAG 不可用，中止。")
        _write_status({"ok": False, "checked_at": now_str, "error": "LightRAG down"})
        sys.exit(1)

    # ── 讀取同步狀態 ──
    state = load_json(SYNC_STATE, {})
    if args.init:
        since_ts = 0.0
        print("📦 Init 模式：掃全部文件")
    else:
        since_ts = state.get("last_synced_ts", 0.0)
        last_str = state.get("last_synced_str", "（從未同步）")
        print(f"⏱  上次同步：{last_str}")

    # ── 掃描 ──
    candidates = scan_vault(since_ts, args.path)
    print(f"📂 找到 {len(candidates)} 個修改文件")

    if not candidates:
        print("✅ 無新文件需要同步。")
        _write_status({"ok": True, "checked_at": now_str, "ingested": 0, "skipped": 0})
        state["last_synced_ts"] = now_ts
        state["last_synced_str"] = now_str
        save_json(SYNC_STATE, state)
        return

    # ── 過濾 + Ingest ──
    ingested = 0
    skipped_short = 0
    errors = 0

    for md_file in candidates:
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        # 字數過濾（Obsidian 中文字數）
        clean_len = len(text.strip())
        if clean_len < MIN_CHARS:
            skipped_short += 1
            continue

        title = build_title(md_file)
        rel_path = md_file.relative_to(OBSIDIAN_VAULT)

        if args.dry_run:
            print(f"   DRY  {rel_path}  ({clean_len} chars)")
            ingested += 1
            continue

        ok, detail = lightrag_ingest(title, text)
        if ok:
            ingested += 1
            print(f"   ✅  {rel_path}  ({clean_len} chars)")
        else:
            errors += 1
            print(f"   ❌  {rel_path}: {detail}")

        # 避免 LightRAG rate-limit
        time.sleep(0.5)

    # ── 更新狀態 ──
    print(f"\n📊 結果：ingest {ingested}｜太短跳過 {skipped_short}｜錯誤 {errors}")

    if not args.dry_run:
        state["last_synced_ts"] = now_ts
        state["last_synced_str"] = now_str
        state["last_run"] = {
            "ingested": ingested,
            "skipped_short": skipped_short,
            "errors": errors,
            "total_candidates": len(candidates),
        }
        save_json(SYNC_STATE, state)

    _write_status({
        "ok": errors == 0,
        "checked_at": now_str,
        "ingested": ingested,
        "skipped": skipped_short,
        "errors": errors,
    })

    sys.exit(0 if errors == 0 else 1)


def _write_status(data: dict) -> None:
    status = load_json(STATUS_FILE, {})
    status["obsidian_ingest"] = data
    save_json(STATUS_FILE, status)
    print(f"💾 狀態已寫入 system-status.json[obsidian_ingest]")


if __name__ == "__main__":
    main()

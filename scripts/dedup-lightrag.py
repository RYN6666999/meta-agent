#!/usr/bin/env python3
"""
dedup-lightrag.py — P4-B 實體去重腳本
每週掃描 LightRAG 知識圖譜，找出相似實體並合併

執行方式：
  python3 scripts/dedup-lightrag.py
  python3 scripts/dedup-lightrag.py --dry-run  # 只列出，不合併
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

import httpx

META = Path("/Users/ryan/meta-agent")
LOG_FILE = META / "memory" / "dedup-log.md"
COMPAT_STORE = META / "memory" / "lightrag-compat-store.jsonl"

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from common.config import LIGHTRAG_API as CONFIG_LIGHTRAG_API
except Exception:
    CONFIG_LIGHTRAG_API = "http://127.0.0.1:9631"

LIGHTRAG_API = os.environ.get("LIGHTRAG_API", CONFIG_LIGHTRAG_API)

# 相似度閾值：兩個實體名稱「包含」關係或極短 Levenshtein 距離視為重複
SIMILARITY_THRESHOLD = 0.8


def levenshtein(a: str, b: str) -> float:
    """回傳 0~1 的相似度（1 = 完全相同）"""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    dp = list(range(lb + 1))
    for i, ca in enumerate(a):
        ndp = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            ndp.append(min(ndp[j] + 1, dp[j + 1] + 1, dp[j] + cost))
        dp = ndp
    dist = dp[lb]
    return 1.0 - dist / max(la, lb)


def fetch_entities() -> list[dict]:
    """從 LightRAG 取得所有實體"""
    endpoints = [
        f"{LIGHTRAG_API}/graphs",
        f"{LIGHTRAG_API}/entities",
    ]

    for endpoint in endpoints:
        try:
            resp = httpx.get(endpoint, timeout=8)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            # LightRAG graph API 結構
            nodes = data.get("nodes") or data.get("entities") or []
            if isinstance(nodes, list):
                return nodes
        except Exception as e:
            print(f"⚠️  讀取 {endpoint} 失敗: {e}", file=sys.stderr)

    # compat server 沒有 /graphs；退回用已 ingest 文件描述做最小實體視角
    if COMPAT_STORE.exists():
        entities = []
        for line in COMPAT_STORE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            name = str(row.get("description") or row.get("title") or "").strip()
            if not name:
                continue
            entities.append({"id": name, "type": "DOCUMENT"})
        if entities:
            print("ℹ️  使用 compat store 進行去重分析", file=sys.stderr)
            return entities

    print("❌ 無法連接 LightRAG 或取得實體", file=sys.stderr)
    return []


def find_duplicates(entities: list[dict]) -> list[tuple[dict, dict, float]]:
    """找出相似實體對，回傳 (entity_a, entity_b, similarity)"""
    duplicates = []
    names = [(e, e.get("id") or e.get("name") or "") for e in entities]

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            e_a, name_a = names[i]
            e_b, name_b = names[j]
            if not name_a or not name_b:
                continue
            # 同名實體另外做摘要統計，避免在 pair-list 產生大量噪音
            if name_a.lower().strip() == name_b.lower().strip():
                continue

            sim = levenshtein(name_a, name_b)
            # 也檢查包含關係
            if name_a.lower() in name_b.lower() or name_b.lower() in name_a.lower():
                sim = max(sim, 0.85)

            if sim >= SIMILARITY_THRESHOLD:
                duplicates.append((e_a, e_b, sim))

    return duplicates


def summarize_exact_duplicates(entities: list[dict]) -> dict[str, int]:
    """統計同名重複（名稱完全相同，count>1）"""
    counter: dict[str, int] = defaultdict(int)
    for e in entities:
        name = (e.get("id") or e.get("name") or "").strip()
        if not name:
            continue
        counter[name] += 1
    return {name: cnt for name, cnt in counter.items() if cnt > 1}


def group_by_type(entities: list[dict]) -> dict[str, list]:
    """按類型分組實體"""
    groups = defaultdict(list)
    for e in entities:
        etype = e.get("type") or e.get("entity_type") or "UNKNOWN"
        groups[etype].append(e)
    return dict(groups)


def write_dedup_log(duplicates: list, stats: dict, dry_run: bool):
    """寫入去重日誌"""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mode_str = "DRY RUN（只分析，未修改）" if dry_run else "已執行合併"

    lines = [
        f"---",
        f"date: {date.today()}",
        f"type: dedup_report",
        f"mode: {'dry_run' if dry_run else 'executed'}",
        f"---",
        f"",
        f"# LightRAG 去重報告 {ts}",
        f"",
        f"**模式**：{mode_str}",
        f"**總實體數**：{stats.get('total', 0)}",
        f"**發現重複對**：{len(duplicates)}",
        f"**同名重複群組**：{stats.get('exact_name_groups', 0)}",
        f"",
        f"## 同名重複摘要",
        f"",
    ]

    exact_duplicates = stats.get("exact_duplicates", {})
    if exact_duplicates:
        for name, cnt in sorted(exact_duplicates.items(), key=lambda item: item[1], reverse=True)[:20]:
            lines.append(f"- `{name}` x{cnt}")
    else:
        lines.append("✅ 未發現同名重複")

    lines.extend([
        f"",
        f"## 重複實體清單",
        f"",
    ])

    if not duplicates:
        lines.append("✅ 未發現重複實體")
    else:
        for a, b, sim in duplicates[:50]:  # 最多顯示 50 對
            name_a = a.get("id") or a.get("name") or "?"
            name_b = b.get("id") or b.get("name") or "?"
            lines.append(f"- `{name_a}` ↔ `{name_b}` (相似度 {sim:.2f})")

    content = "\n".join(lines) + "\n"

    # 追加到日誌（保留歷史）
    if LOG_FILE.exists():
        existing = LOG_FILE.read_text(encoding="utf-8")
        LOG_FILE.write_text(content + "\n---\n\n" + existing, encoding="utf-8")
    else:
        LOG_FILE.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="LightRAG 實體去重腳本")
    parser.add_argument("--dry-run", action="store_true", help="只分析，不執行合併")
    args = parser.parse_args()

    print(f"🔍 連接 LightRAG {LIGHTRAG_API}...")
    entities = fetch_entities()

    if not entities:
        print("⚠️  無法取得實體列表（LightRAG 可能未運行或 API 路徑不同）")
        # 仍寫入日誌記錄嘗試
        write_dedup_log([], {"total": 0, "error": "cannot connect"}, args.dry_run)
        sys.exit(0)

    print(f"📊 共 {len(entities)} 個實體")

    # 按類型分組統計
    groups = group_by_type(entities)
    for etype, items in sorted(groups.items()):
        print(f"  {etype}: {len(items)} 個")

    print("🔎 掃描重複實體...")
    exact_duplicates = summarize_exact_duplicates(entities)
    if exact_duplicates:
        print(f"🧩 同名重複群組 {len(exact_duplicates)} 組")
        for name, cnt in sorted(exact_duplicates.items(), key=lambda item: item[1], reverse=True)[:10]:
            print(f"  {name} x{cnt}")
    duplicates = find_duplicates(entities)

    if not duplicates:
        print("✅ 未發現重複實體")
    else:
        print(f"⚠️  發現 {len(duplicates)} 對相似實體：")
        for a, b, sim in duplicates[:20]:
            name_a = a.get("id") or a.get("name") or "?"
            name_b = b.get("id") or b.get("name") or "?"
            print(f"  {name_a} ↔ {name_b} ({sim:.2f})")

        if not args.dry_run:
            print("📝 LightRAG 目前不支援直接 API 合併實體。")
            print("   重複實體已記錄到日誌，請手動在 WebUI 處理：")
            print(f"   {LIGHTRAG_API}/webui")
        else:
            print("（dry-run 模式，未修改任何資料）")

    write_dedup_log(
        duplicates,
        {
            "total": len(entities),
            "exact_name_groups": len(exact_duplicates),
            "exact_duplicates": exact_duplicates,
        },
        args.dry_run,
    )
    print(f"📄 報告已寫入 {LOG_FILE}")


if __name__ == "__main__":
    main()

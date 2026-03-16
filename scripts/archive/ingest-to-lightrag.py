#!/usr/bin/env python3
"""
meta-agent 知識圖譜建置器
將所有寶貴記憶 ingest 進 LightRAG，建立真正的大腦
"""

import requests
import json
import time
from pathlib import Path

LIGHTRAG_URL = "http://localhost:9621"
META_DIR = Path("/Users/ryan/meta-agent")
OBSIDIAN_DIR = Path("/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun")

# 要 ingest 的文件（按重要性排序）
SOURCES = [
    {
        "title": "【遺產】零幻覺迭代元代理模組 meta-agent 完整架構討論",
        "path": OBSIDIAN_DIR / "TikTok_Notes/零幻覺迭代元代理模組meta-agent計畫.md",
        "type": "tech_decision",
        "priority": 1
    },
    {
        "title": "【遺產】元 agent 架構定義文件",
        "path": OBSIDIAN_DIR / "元agent.md",
        "type": "tech_decision",
        "priority": 1
    },
    {
        "title": "【法典】meta-agent law.json 硬規則",
        "path": META_DIR / "law.json",
        "type": "rule",
        "priority": 1
    },
    {
        "title": "【錯誤庫】Douyin Parser Bug 根因文檔",
        "path": META_DIR / "error-log/douyin-parser-bugs.md",
        "type": "error_fix",
        "priority": 2
    },
    {
        "title": "【技術棧】Douyin Parser 技術棧與路徑",
        "path": META_DIR / "tech-stack/douyin-parser.md",
        "type": "tech_decision",
        "priority": 2
    },
    {
        "title": "【決策比較】LightRAG vs Neo4j",
        "path": META_DIR / "tech-stack/alternatives/lightrag-vs-neo4j-comparison-2026-03-15.md",
        "type": "tech_decision",
        "priority": 2
    },
    {
        "title": "【決策比較】Dify Cloud vs 自架",
        "path": META_DIR / "tech-stack/alternatives/dify-cloud-vs-selfhost-comparison-2026-03-15.md",
        "type": "tech_decision",
        "priority": 2
    },
    {
        "title": "【記憶規則】清洗與分類規範",
        "path": META_DIR / "memory/cleaning-rules.md",
        "type": "rule",
        "priority": 3
    },
]

def ingest_document(title, content, doc_type):
    """POST 文件到 LightRAG"""
    payload = {
        "text": f"# {title}\n\n類型：{doc_type}\n\n{content}",
        "description": title
    }
    try:
        resp = requests.post(
            f"{LIGHTRAG_URL}/documents/text",
            json=payload,
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("id", "unknown")
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)

def check_health():
    try:
        resp = requests.get(f"{LIGHTRAG_URL}/health", timeout=5)
        return resp.status_code == 200
    except:
        return False

def main():
    print("🧠 meta-agent 知識圖譜建置器")
    print("=" * 50)

    if not check_health():
        print("❌ LightRAG 不可用，請確認服務運行中")
        return 1

    print("✅ LightRAG 連線正常\n")
    results = []

    for source in SOURCES:
        path = source["path"]
        title = source["title"]

        if not path.exists():
            print(f"⚠️  跳過（找不到）：{title}")
            results.append({"title": title, "status": "skip"})
            continue

        content = path.read_text(encoding="utf-8")
        word_count = len(content)

        print(f"📥 Ingest: {title}")
        print(f"   字數：{word_count:,}")

        success, info = ingest_document(title, content, source["type"])

        if success:
            print(f"   ✅ 成功（track_id: {info}）")
            results.append({"title": title, "status": "ok", "id": info})
        else:
            print(f"   ❌ 失敗：{info}")
            results.append({"title": title, "status": "fail", "error": info})

        # 避免打爆 API
        time.sleep(2)

    print("\n" + "=" * 50)
    ok = sum(1 for r in results if r["status"] == "ok")
    skip = sum(1 for r in results if r["status"] == "skip")
    fail = sum(1 for r in results if r["status"] == "fail")
    print(f"📊 結果：✅ {ok} 成功 / ⚠️ {skip} 跳過 / ❌ {fail} 失敗")

    # 等待圖譜建立
    if ok > 0:
        print("\n⏳ 等待 LightRAG 建立知識圖譜（約 30-60 秒）...")
        time.sleep(10)

        # 查詢文件數
        try:
            resp = requests.get(f"{LIGHTRAG_URL}/documents", timeout=10)
            if resp.status_code == 200:
                docs = resp.json()
                total = len(docs.get("statuses", []))
                print(f"✅ LightRAG 現有文件：{total} 份")
        except:
            pass

        # 測試查詢
        print("\n🔍 測試語意查詢：「n8n OOM 崩潰怎麼解決？」")
        try:
            resp = requests.post(
                f"{LIGHTRAG_URL}/query",
                json={"query": "n8n OOM 崩潰怎麼解決", "mode": "hybrid", "top_k": 3},
                timeout=60
            )
            if resp.status_code == 200:
                result = resp.json()
                answer = result.get("response", "")[:300]
                print(f"   回答：{answer}...")
            else:
                print(f"   查詢失敗：HTTP {resp.status_code}")
        except Exception as e:
            print(f"   查詢異常：{e}")

    return 0

if __name__ == "__main__":
    exit(main())

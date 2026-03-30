#!/usr/bin/env python3
"""
scripts/index_vectors.py
=========================
將 SQLite 中所有場景分析卡索引到 ChromaDB 向量庫（首次使用前必須執行一次）。

用法：
    # 全量索引（首次）
    python scripts/index_vectors.py

    # 指定書籍
    python scripts/index_vectors.py --book_id <book_id>

    # 清空重建（分析資料有大幅更新時）
    python scripts/index_vectors.py --reset

    # 使用更高品質的中文模型（檔案較大，~570MB）
    python scripts/index_vectors.py --model BAAI/bge-m3

參數：
    --db         SQLite 路徑（預設：novel_analyzer.db）
    --store      ChromaDB 存放路徑（預設：vector_store/chroma）
    --book_id    只索引特定書籍（留空 = 全部）
    --model      embedding 模型（預設：paraphrase-multilingual-MiniLM-L12-v2）
    --reset      先清空向量庫再重建
    --batch_size 每批 upsert 筆數（預設：50）
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Index novel scenes into ChromaDB")
    p.add_argument("--db", default=str(BASE_DIR / "novel_analyzer.db"), help="SQLite 路徑")
    p.add_argument(
        "--store",
        default=str(BASE_DIR / "vector_store" / "chroma"),
        help="ChromaDB 持久化路徑",
    )
    p.add_argument("--book_id", default=None, help="只索引指定書籍")
    p.add_argument(
        "--model",
        default="paraphrase-multilingual-MiniLM-L12-v2",
        help="sentence-transformers 模型名稱",
    )
    p.add_argument("--reset", action="store_true", help="清空現有向量庫後重建")
    p.add_argument("--batch_size", type=int, default=50, help="每批 upsert 筆數")
    return p.parse_args()


async def run(args: argparse.Namespace) -> None:
    # 延後 import，讓缺少依賴時的錯誤訊息更清晰
    try:
        from services.vector_store.chroma_adapter import ChromaAdapter, build_chunk_from_scene
    except ImportError as e:
        print(f"\n❌ 缺少依賴：{e}")
        print("請先安裝：pip install chromadb sentence-transformers")
        sys.exit(1)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ 找不到資料庫：{db_path}")
        sys.exit(1)

    print(f"🔧 初始化向量庫（模型：{args.model}）...")
    print("   首次執行會自動下載 embedding 模型，請耐心等候。")
    adapter = ChromaAdapter(persist_path=args.store, model_name=args.model)

    if args.reset:
        print("⚠️  清空現有向量庫...")
        adapter._client.delete_collection(COLLECTION_NAME := adapter._col.name)
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        adapter._col = adapter._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=adapter._ef,
            metadata={"hnsw:space": "cosine"},
        )
        print("   向量庫已清空。")

    # 查詢 SQLite
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM scene_framework_cards"
    params: tuple = ()
    if args.book_id:
        query += " WHERE book_id = ?"
        params = (args.book_id,)
    query += " ORDER BY chapter_number, scene_number"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    total = len(rows)
    if total == 0:
        print("⚠️  資料庫中沒有場景卡，請先執行批次分析。")
        return

    print(f"📚 共 {total} 筆場景卡待索引")
    if args.book_id:
        print(f"   書籍篩選：{args.book_id}")

    batch_size = max(1, args.batch_size)
    indexed = 0
    batch = []

    for i, row in enumerate(rows):
        batch.append(build_chunk_from_scene(dict(row)))
        if len(batch) >= batch_size:
            ids = await adapter.index_chunks(batch)
            indexed += len(ids)
            pct = indexed * 100 // total
            print(f"  [{pct:3d}%] 已索引 {indexed}/{total}")
            batch = []

    if batch:
        ids = await adapter.index_chunks(batch)
        indexed += len(ids)

    print(f"\n✅ 索引完成！共 {indexed} 筆，向量庫現有 {adapter.count} 筆。")
    print(f"   存放路徑：{args.store}")
    print("\n現在可以啟動 MCP server：")
    print("   python mcp_server.py")


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

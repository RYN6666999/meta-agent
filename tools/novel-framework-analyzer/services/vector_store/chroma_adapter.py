"""
services/vector_store/chroma_adapter.py
========================================
ChromaDB 本地向量庫 adapter。

實作 AbstractVectorStore，使用 sentence-transformers 做 embedding。
支援中文的多語言模型 paraphrase-multilingual-MiniLM-L12-v2（~270MB，首次建立時自動下載）。

安裝依賴：
    pip install chromadb sentence-transformers

使用範例：
    adapter = ChromaAdapter(persist_path="./vector_store/chroma")
    # 索引（執行一次）
    await adapter.index_chunks(chunks)
    # 語義搜尋
    results = await adapter.retrieve(RetrievalRequest(query="謝雲初的欲望"))
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from services.vector_store.base import (
    AbstractVectorStore,
    ChunkMetadata,
    IndexedChunk,
    RetrievalRequest,
    RetrievalResult,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "novel_scenes"


class ChromaAdapter(AbstractVectorStore):
    """
    ChromaDB 本地向量庫 adapter。
    - 使用 cosine similarity
    - 支援 metadata 過濾（book_id、chapter_number 等）
    - Upsert-safe：重複索引不會產生重複記錄
    """

    def __init__(self, persist_path: str, model_name: str = DEFAULT_MODEL) -> None:
        self._client = chromadb.PersistentClient(path=persist_path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=model_name)
        self._col = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaAdapter 已連線，集合 %s 共 %d 筆", COLLECTION_NAME, self._col.count())

    @property
    def count(self) -> int:
        return self._col.count()

    # ── AbstractVectorStore 實作 ─────────────────────────────────────────────

    async def index_chunks(self, chunks: List[IndexedChunk]) -> List[str]:
        """批次 upsert chunks，返回成功入庫的 chunk_id 列表"""
        if not chunks:
            return []

        ids = [c.chunk_id for c in chunks]
        texts = [c.text for c in chunks]
        metadatas = [
            {
                "book_id": c.metadata.book_id,
                "chapter_number": c.metadata.chapter_number,
                "scene_id": c.metadata.scene_id,
                "scene_number": c.metadata.scene_number,
                "chunk_index": c.metadata.chunk_index,
                "focal_characters": json.dumps(c.metadata.focal_characters, ensure_ascii=False),
                "match_level": c.metadata.match_level or "",
                "confidence": float(c.metadata.confidence or 0.0),
            }
            for c in chunks
        ]
        self._col.upsert(ids=ids, documents=texts, metadatas=metadatas)
        return ids

    async def retrieve(self, request: RetrievalRequest) -> List[RetrievalResult]:
        """執行向量檢索，返回 top-k 相似場景"""
        # 建構 ChromaDB where 過濾條件
        where: Optional[dict] = None
        if request.filters:
            clauses = [{k: {"$eq": v}} for k, v in request.filters.items() if v is not None]
            if len(clauses) == 1:
                where = clauses[0]
            elif len(clauses) > 1:
                where = {"$and": clauses}

        results = self._col.query(
            query_texts=[request.query],
            n_results=min(request.top_k, self._col.count() or 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        output: List[RetrievalResult] = []
        for i, doc in enumerate(results["documents"][0]):
            # ChromaDB cosine distance → similarity
            score = 1.0 - results["distances"][0][i]
            if score < request.score_threshold:
                continue

            meta = results["metadatas"][0][i]
            output.append(
                RetrievalResult(
                    chunk_id=results["ids"][0][i],
                    text=doc,
                    score=score,
                    metadata=ChunkMetadata(
                        book_id=meta.get("book_id", ""),
                        chapter_number=int(meta.get("chapter_number", 0)),
                        scene_id=meta.get("scene_id", ""),
                        scene_number=int(meta.get("scene_number", 0)),
                        chunk_index=int(meta.get("chunk_index", 0)),
                        focal_characters=json.loads(meta.get("focal_characters", "[]")),
                        match_level=meta.get("match_level") or None,
                        confidence=float(meta.get("confidence", 0.0)),
                    ),
                    source_reference=f"第{meta.get('chapter_number')}章 場景{meta.get('scene_number')}",
                )
            )
        return output

    async def delete_by_scene(self, scene_id: str) -> int:
        """刪除指定 scene_id 的所有 chunks"""
        before = self._col.count()
        self._col.delete(where={"scene_id": {"$eq": scene_id}})
        return before - self._col.count()

    async def update_metadata(self, chunk_id: str, metadata_update: dict) -> bool:
        """更新某 chunk 的 metadata"""
        try:
            self._col.update(ids=[chunk_id], metadatas=[metadata_update])
            return True
        except Exception as e:
            logger.warning("update_metadata failed for %s: %s", chunk_id, e)
            return False

    async def health_check(self) -> bool:
        """確認 ChromaDB 是否可用"""
        try:
            self._col.count()
            return True
        except Exception:
            return False


# ── 工具函式 ─────────────────────────────────────────────────────────────────

def build_chunk_from_scene(row: dict) -> IndexedChunk:
    """
    將 SQLite scene_framework_cards 的一筆記錄轉為 IndexedChunk。

    embedding 文本 = 場景原文（前 400 字）+ 情境 + 欲望 + 心理轉變描述
    保留足夠語義讓向量搜尋找到心理狀態相關場景。
    """

    def _parse(field: str) -> dict:
        val = row.get(field)
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    parts: List[str] = []

    scene_text = row.get("scene_text", "")
    if scene_text:
        parts.append(f"場景原文：{scene_text[:400]}")

    sit = _parse("situation")
    if sit.get("description"):
        parts.append(f"情境：{sit['description']}")

    des = _parse("desire")
    if des.get("description"):
        parts.append(f"欲望：{des['description']}")

    ms = _parse("mind_shift")
    if ms.get("description"):
        parts.append(f"心理轉變：{ms['description']}")

    focal = row.get("focal_character")
    if focal:
        parts.append(f"主角：{focal}")

    text = "\n".join(parts) if parts else scene_text[:600]

    return IndexedChunk(
        chunk_id=row["id"],        # 使用 SQLite PK 作為 chunk_id，方便回查
        text=text,
        metadata=ChunkMetadata(
            book_id=row.get("book_id", ""),
            chapter_number=row.get("chapter_number", 0),
            scene_id=row.get("id", ""),   # 同 chunk_id，方便 MCP server 回查
            scene_number=row.get("scene_number", 0),
            chunk_index=0,
            focal_characters=[focal] if focal else [],
            match_level=row.get("match_level"),
            confidence=row.get("confidence_score"),
        ),
    )

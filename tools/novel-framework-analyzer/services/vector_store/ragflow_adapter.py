"""
services/vector_store/ragflow_adapter.py
=========================================
RAGFlow 的具體 adapter 實作。

RAGFlow API 端點（預設本地）：
  - POST /v1/datasets/{dataset_id}/documents  ← 上傳文件
  - POST /v1/datasets/{dataset_id}/chunks     ← 手動 chunk 入庫（本系統使用）
  - POST /v1/retrieval                         ← 執行檢索
  - DELETE /v1/datasets/{dataset_id}/chunks   ← 刪除 chunks

設計決策：
- 本系統由後端自行切 chunk，不使用 RAGFlow 的自動切分
- metadata 以 RAGFlow 的 custom_fields 存儲
- hybrid retrieval 使用 RAGFlow 內建的 BM25 + dense 混合模式
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from services.vector_store.base import (
    AbstractVectorStore,
    ChunkMetadata,
    IndexedChunk,
    RetrievalRequest,
    RetrievalResult,
)

logger = logging.getLogger(__name__)


class RAGFlowAdapter(AbstractVectorStore):
    """
    RAGFlow HTTP API adapter。

    使用方式：
        adapter = RAGFlowAdapter(base_url="http://localhost:9380", api_key="...")
        await adapter.index_chunks(chunks)
        results = await adapter.retrieve(RetrievalRequest(query="謝雲初的欲望"))
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        dataset_id: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset_id = dataset_id
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # AbstractVectorStore 實作
    # ------------------------------------------------------------------

    async def index_chunks(self, chunks: List[IndexedChunk]) -> List[str]:
        """
        批次上傳 chunks 到 RAGFlow dataset。
        RAGFlow 支援批次 upsert，每次最多 100 筆。
        """
        if not chunks:
            return []

        indexed_ids: List[str] = []
        batch_size = 100

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            payload = {
                "chunks": [
                    {
                        "id": c.chunk_id,
                        "content": c.text,
                        "document_id": c.metadata.book_id,
                        "metadata": self._serialize_metadata(c.metadata),
                    }
                    for c in batch
                ]
            }

            try:
                resp = await self._client.post(
                    f"/v1/datasets/{self.dataset_id}/chunks",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                indexed_ids.extend(
                    item["id"] for item in data.get("chunks", [])
                )
                logger.info(f"RAGFlow 入庫 {len(batch)} chunks，batch {i // batch_size + 1}")

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"RAGFlow chunk 入庫失敗 (batch {i // batch_size + 1})："
                    f"{e.response.status_code} {e.response.text[:200]}"
                )
                raise

        return indexed_ids

    async def retrieve(self, request: RetrievalRequest) -> List[RetrievalResult]:
        """
        呼叫 RAGFlow retrieval API。
        支援 hybrid / dense / sparse 三種模式。
        """
        payload: Dict[str, Any] = {
            "question": request.query,
            "datasets": [self.dataset_id],
            "top_k": request.top_k,
            "similarity_threshold": request.score_threshold,
            "vector_similarity_weight": (
                0.7 if request.search_mode == "hybrid"
                else (1.0 if request.search_mode == "dense" else 0.0)
            ),
            "highlight": False,
        }

        # 加入 metadata 過濾（RAGFlow 支援 keyword filters）
        if request.filters:
            payload["condition"] = self._build_filter_condition(request.filters)

        try:
            resp = await self._client.post("/v1/retrieval", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"RAGFlow retrieval 失敗：{e.response.text[:300]}")
            raise

        return [
            RetrievalResult(
                chunk_id=item["id"],
                text=item["content"],
                score=item.get("similarity", 0.0),
                metadata=self._deserialize_metadata(item.get("metadata", {})),
                source_reference=self._build_source_reference(item.get("metadata", {})),
            )
            for item in data.get("chunks", [])
        ]

    async def delete_by_scene(self, scene_id: str) -> int:
        """刪除某場景的所有 chunks"""
        # 先查詢該 scene_id 的所有 chunk_ids
        search_resp = await self._client.get(
            f"/v1/datasets/{self.dataset_id}/chunks",
            params={"filter": f"scene_id={scene_id}", "page_size": 500},
        )
        search_resp.raise_for_status()
        chunk_ids = [c["id"] for c in search_resp.json().get("chunks", [])]

        if not chunk_ids:
            return 0

        delete_resp = await self._client.delete(
            f"/v1/datasets/{self.dataset_id}/chunks",
            json={"ids": chunk_ids},
        )
        delete_resp.raise_for_status()
        logger.info(f"已從 RAGFlow 刪除場景 {scene_id} 的 {len(chunk_ids)} 個 chunks")
        return len(chunk_ids)

    async def update_metadata(
        self, chunk_id: str, metadata_update: Dict[str, Any]
    ) -> bool:
        """更新單一 chunk 的 metadata"""
        resp = await self._client.patch(
            f"/v1/datasets/{self.dataset_id}/chunks/{chunk_id}",
            json={"metadata": metadata_update},
        )
        if resp.status_code == 200:
            return True
        logger.warning(
            f"RAGFlow metadata 更新失敗 chunk={chunk_id}：{resp.status_code}"
        )
        return False

    async def health_check(self) -> bool:
        """確認 RAGFlow 服務可達"""
        try:
            resp = await self._client.get("/v1/datasets", timeout=5.0)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"RAGFlow health check 失敗：{e}")
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_metadata(meta: ChunkMetadata) -> Dict[str, Any]:
        """將 ChunkMetadata 序列化為 RAGFlow 可存的 dict"""
        return {
            "book_id": meta.book_id,
            "chapter_number": str(meta.chapter_number),
            "scene_id": meta.scene_id,
            "scene_number": str(meta.scene_number),
            "chunk_index": str(meta.chunk_index),
            "focal_characters": ",".join(meta.focal_characters),
            "match_level": meta.match_level or "",
            "confidence": str(meta.confidence or ""),
            "source_path": meta.source_path or "",
            **{f"extra_{k}": str(v) for k, v in meta.extra.items()},
        }

    @staticmethod
    def _deserialize_metadata(raw: Dict[str, Any]) -> ChunkMetadata:
        """從 RAGFlow 回傳的 dict 還原 ChunkMetadata"""
        chars_raw = raw.get("focal_characters", "")
        conf_raw = raw.get("confidence", "")
        return ChunkMetadata(
            book_id=raw.get("book_id", ""),
            chapter_number=int(raw.get("chapter_number", 0)),
            scene_id=raw.get("scene_id", ""),
            scene_number=int(raw.get("scene_number", 0)),
            chunk_index=int(raw.get("chunk_index", 0)),
            focal_characters=chars_raw.split(",") if chars_raw else [],
            match_level=raw.get("match_level") or None,
            confidence=float(conf_raw) if conf_raw else None,
            source_path=raw.get("source_path") or None,
        )

    @staticmethod
    def _build_source_reference(metadata: Dict[str, Any]) -> str:
        """建立人類可讀的來源標示"""
        chap = metadata.get("chapter_number", "?")
        scene = metadata.get("scene_number", "?")
        return f"第 {chap} 章 · 場景 {scene}"

    @staticmethod
    def _build_filter_condition(filters: Dict[str, Any]) -> Dict[str, Any]:
        """將 filters dict 轉換為 RAGFlow filter condition 格式"""
        conditions = []
        for key, value in filters.items():
            conditions.append({"field": key, "op": "=", "value": str(value)})
        return {"operator": "AND", "conditions": conditions}

    async def __aenter__(self) -> "RAGFlowAdapter":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

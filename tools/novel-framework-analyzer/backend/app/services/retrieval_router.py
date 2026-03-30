"""
backend/app/services/retrieval_router.py
=========================================
查詢路由服務。

查詢策略（優先序）：
  1. 場景卡快查  — 先從 PostgreSQL 的 scene_framework_cards 查
     (結構化查詢，速度快，含完整分析結果)
  2. RAGFlow 語意檢索 — 若場景卡未命中，從向量庫找相關 chunk
     (覆蓋未分析的場景或跨場景語意匹配)
  3. 合併去重 & rerank — 兩路結果合併，依 score + match_level 排序

Data Flow：
  User Query
    ↓
  QueryRouter.route(query)
    ├─ SceneCardSearcher.search(query)     → PostgreSQL
    └─ VectorSearcher.search(query)        → RAGFlow
        ↓
  ResultMerger.merge(card_results, vector_results)
    ↓
  List[QueryResult] (帶 source_reference)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.vector_store.base import AbstractVectorStore, RetrievalRequest, RetrievalResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """單一查詢結果，統一封裝兩路來源"""
    result_id: str
    text_excerpt: str           # 顯示給用戶的文字片段
    source_reference: str       # 如「第三章 · 場景2」
    relevance_score: float      # 0.0–1.0
    result_type: str            # "scene_card" | "raw_chunk"

    # scene_card 結果的附加欄位
    scene_id: Optional[str] = None
    focal_character: Optional[str] = None
    match_level: Optional[str] = None
    confidence: Optional[float] = None
    framework_summary: Optional[str] = None  # 給 LLM 的簡短框架摘要

    # raw_chunk 結果的附加欄位
    chunk_id: Optional[str] = None
    chapter_number: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryRequest:
    """查詢請求"""
    query: str
    book_id: Optional[str] = None
    chapter_number: Optional[int] = None
    focal_character: Optional[str] = None
    match_level_filter: Optional[str] = None  # 只要符合特定等級的場景
    top_k: int = 5
    include_raw_chunks: bool = True    # 是否同時查 RAGFlow
    card_weight: float = 0.6           # 場景卡結果的權重加成


# ---------------------------------------------------------------------------
# 場景卡 PostgreSQL 查詢器
# ---------------------------------------------------------------------------


class SceneCardSearcher:
    """
    從 PostgreSQL 的 scene_framework_cards 做結構化查詢。
    支援：角色名稱、match_level、confidence 過濾。
    全文搜尋使用 PostgreSQL 的 pg_trgm 相似度（中文場景摘要）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(self, request: QueryRequest) -> List[QueryResult]:
        """
        優先用角色名 + match_level 做精確過濾，
        再用 pg_trgm 做模糊全文匹配。
        """
        from backend.app.models.scene_framework_card import SceneFrameworkCard

        stmt = select(SceneFrameworkCard)

        # 精確過濾條件
        if request.book_id:
            stmt = stmt.where(SceneFrameworkCard.book_id == request.book_id)
        if request.chapter_number:
            stmt = stmt.where(SceneFrameworkCard.chapter_number == request.chapter_number)
        if request.focal_character:
            stmt = stmt.where(
                SceneFrameworkCard.focal_character.ilike(f"%{request.focal_character}%")
            )
        if request.match_level_filter:
            stmt = stmt.where(SceneFrameworkCard.match_level == request.match_level_filter)

        # 對 situation / desire / mind_shift JSONB 做 PostgreSQL 全文搜尋
        # 使用 @> 或 ilike 視場景而定；此處用 JSONB 的 ->> 取文字再模糊匹配
        query_terms = request.query.strip()
        if query_terms:
            # 在 focal_character、situation text、desire text 中搜尋
            stmt = stmt.where(
                or_(
                    SceneFrameworkCard.focal_character.ilike(f"%{query_terms}%"),
                    text(
                        "situation->>'external_situation' ILIKE :q"
                        " OR situation->>'power_dynamics' ILIKE :q"
                        " OR desire->>'explicit_desire' ILIKE :q"
                        " OR desire->>'implicit_desire' ILIKE :q"
                        " OR mind_shift->>'shift_description' ILIKE :q"
                    ).bindparams(q=f"%{query_terms}%"),
                )
            )

        stmt = stmt.order_by(
            SceneFrameworkCard.confidence_score.desc()
        ).limit(request.top_k * 2)  # 多取一些，後續 rerank 用

        result = await self.db.execute(stmt)
        cards = result.scalars().all()

        return [self._card_to_query_result(card) for card in cards[: request.top_k]]

    @staticmethod
    def _card_to_query_result(card: Any) -> QueryResult:
        situation = card.situation or {}
        desire = card.desire or {}
        mind_shift = card.mind_shift or {}

        # 建立給 LLM 的精簡框架摘要
        framework_summary = (
            f"【局】{situation.get('external_situation', '')[:60]}"
            f" 【欲】{desire.get('explicit_desire', '')[:60]}"
            f" 【心變】{mind_shift.get('shift_description', '')[:60]}"
        )

        return QueryResult(
            result_id=card.id,
            text_excerpt=framework_summary,
            source_reference=f"第 {card.chapter_number} 章 · 場景 {card.scene_number}",
            relevance_score=card.confidence_score,
            result_type="scene_card",
            scene_id=card.scene_id,
            focal_character=card.focal_character,
            match_level=card.match_level,
            confidence=card.confidence_score,
            framework_summary=framework_summary,
        )


# ---------------------------------------------------------------------------
# RAGFlow 向量查詢器
# ---------------------------------------------------------------------------


class VectorSearcher:
    """封裝 RAGFlow adapter 的向量查詢"""

    def __init__(self, vector_store: AbstractVectorStore) -> None:
        self.vs = vector_store

    async def search(self, request: QueryRequest) -> List[QueryResult]:
        filters: Dict[str, Any] = {}
        if request.book_id:
            filters["book_id"] = request.book_id
        if request.chapter_number:
            filters["chapter_number"] = request.chapter_number
        if request.focal_character:
            filters["focal_characters"] = request.focal_character

        retrieval_request = RetrievalRequest(
            query=request.query,
            top_k=request.top_k,
            score_threshold=0.55,
            filters=filters,
            search_mode="hybrid",
        )

        try:
            results = await self.vs.retrieve(retrieval_request)
        except Exception as e:
            logger.warning(f"RAGFlow 向量查詢失敗，跳過：{e}")
            return []

        return [self._result_to_query_result(r) for r in results]

    @staticmethod
    def _result_to_query_result(r: RetrievalResult) -> QueryResult:
        return QueryResult(
            result_id=r.chunk_id,
            text_excerpt=r.text[:300],
            source_reference=r.source_reference,
            relevance_score=r.score,
            result_type="raw_chunk",
            scene_id=r.metadata.scene_id or None,
            chapter_number=r.metadata.chapter_number,
            chunk_id=r.chunk_id,
            match_level=r.metadata.match_level,
            confidence=r.metadata.confidence,
        )


# ---------------------------------------------------------------------------
# 結果合併與 rerank
# ---------------------------------------------------------------------------


class ResultMerger:
    """合併兩路查詢結果，去重，依加權 score 排序"""

    @staticmethod
    def merge(
        card_results: List[QueryResult],
        vector_results: List[QueryResult],
        card_weight: float = 0.6,
        top_k: int = 5,
    ) -> List[QueryResult]:
        """
        合併策略：
        1. scene_card 結果的 score 乘以 card_weight 加成
        2. 若 raw_chunk 與某 scene_card 屬同一 scene_id，去除 raw_chunk
        3. 最終依加權 score 排序，取 top_k
        """
        seen_scene_ids: set[str] = set()
        merged: List[QueryResult] = []

        # 先處理場景卡（加權）
        for r in card_results:
            r.relevance_score = min(1.0, r.relevance_score * (1 + card_weight))
            if r.scene_id:
                seen_scene_ids.add(r.scene_id)
            merged.append(r)

        # 加入 raw chunks（過濾已有場景卡覆蓋的 scene）
        for r in vector_results:
            if r.scene_id and r.scene_id in seen_scene_ids:
                continue  # 場景卡已覆蓋，跳過
            merged.append(r)

        # 排序
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        return merged[:top_k]


# ---------------------------------------------------------------------------
# 主路由器
# ---------------------------------------------------------------------------


class RetrievalRouter:
    """
    查詢路由主入口。
    編排 SceneCardSearcher + VectorSearcher + ResultMerger。

    典型使用：
        router = RetrievalRouter(db=db_session, vector_store=ragflow_adapter)
        results = await router.route(QueryRequest(query="謝雲初的欲望"))
    """

    def __init__(
        self,
        db: AsyncSession,
        vector_store: AbstractVectorStore,
    ) -> None:
        self.card_searcher = SceneCardSearcher(db)
        self.vector_searcher = VectorSearcher(vector_store)
        self.merger = ResultMerger()

    async def route(self, request: QueryRequest) -> List[QueryResult]:
        """
        執行雙路查詢並合併結果。
        若 include_raw_chunks=False，只查場景卡（適合純框架分析查詢）。
        """
        logger.debug(f"路由查詢：'{request.query[:50]}' book={request.book_id}")

        card_results = await self.card_searcher.search(request)
        logger.debug(f"場景卡命中：{len(card_results)} 筆")

        vector_results: List[QueryResult] = []
        if request.include_raw_chunks:
            vector_results = await self.vector_searcher.search(request)
            logger.debug(f"向量庫命中：{len(vector_results)} 筆")

        merged = self.merger.merge(
            card_results,
            vector_results,
            card_weight=request.card_weight,
            top_k=request.top_k,
        )

        logger.info(
            f"查詢完成：'{request.query[:50]}' → "
            f"{len(merged)} 筆結果（card={len(card_results)} vec={len(vector_results)}）"
        )
        return merged

    async def route_for_chat(
        self,
        query: str,
        book_id: Optional[str] = None,
        focal_character: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        為聊天 API 封裝的便利方法。
        返回適合直接傳給 LLM 作為 context 的格式。
        """
        request = QueryRequest(
            query=query,
            book_id=book_id,
            focal_character=focal_character,
            top_k=5,
            include_raw_chunks=True,
        )
        results = await self.route(request)

        context_blocks = []
        for i, r in enumerate(results, 1):
            if r.result_type == "scene_card":
                block = (
                    f"[來源 {i}] {r.source_reference}"
                    f"（角色：{r.focal_character}，框架符合：{r.match_level}，"
                    f"信心：{r.confidence:.2f}）\n"
                    f"{r.framework_summary}"
                )
            else:
                block = (
                    f"[來源 {i}] {r.source_reference}（原文片段）\n"
                    f"{r.text_excerpt}"
                )
            context_blocks.append(block)

        return {
            "context": "\n\n---\n\n".join(context_blocks),
            "sources": [
                {
                    "index": i + 1,
                    "reference": r.source_reference,
                    "type": r.result_type,
                    "score": round(r.relevance_score, 4),
                }
                for i, r in enumerate(results)
            ],
            "raw_results": results,
        }

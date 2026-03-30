"""
services/vector_store/base.py
==============================
向量庫抽象介面。
所有向量庫實作（RAGFlow、Qdrant、Weaviate 等）都必須實作此介面，
確保上層業務邏輯與具體向量庫解耦。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChunkMetadata:
    """chunk 的 metadata 結構，存入向量庫時的標準格式"""
    book_id: str
    chapter_number: int
    scene_id: str
    scene_number: int
    chunk_index: int           # 在場景中的 chunk 序號
    focal_characters: List[str] = field(default_factory=list)
    match_level: Optional[str] = None   # 若已分析，快查用
    confidence: Optional[float] = None
    source_path: Optional[str] = None   # 原始檔案路徑
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexedChunk:
    """已入庫的 chunk"""
    chunk_id: str
    text: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None


@dataclass
class RetrievalResult:
    """單一檢索結果"""
    chunk_id: str
    text: str
    score: float              # 相似度分數，越高越相關
    metadata: ChunkMetadata
    source_reference: str     # 給前端顯示的來源標示，如「第三章 場景2」


@dataclass
class RetrievalRequest:
    """檢索請求"""
    query: str
    top_k: int = 5
    score_threshold: float = 0.6
    filters: Dict[str, Any] = field(default_factory=dict)  # metadata 過濾條件
    search_mode: str = "hybrid"  # "dense" | "sparse" | "hybrid"


class AbstractVectorStore(ABC):
    """向量庫操作的抽象介面"""

    @abstractmethod
    async def index_chunks(self, chunks: List[IndexedChunk]) -> List[str]:
        """
        批次入庫 chunks。
        Returns: 成功入庫的 chunk_id 列表
        """
        ...

    @abstractmethod
    async def retrieve(self, request: RetrievalRequest) -> List[RetrievalResult]:
        """執行向量檢索，返回 top-k 結果"""
        ...

    @abstractmethod
    async def delete_by_scene(self, scene_id: str) -> int:
        """刪除某個場景的所有 chunks，返回刪除數量"""
        ...

    @abstractmethod
    async def update_metadata(
        self, chunk_id: str, metadata_update: Dict[str, Any]
    ) -> bool:
        """更新某 chunk 的 metadata（如分析完成後寫入 match_level）"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """連線健康確認"""
        ...

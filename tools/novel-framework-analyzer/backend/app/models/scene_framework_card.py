"""
scene_framework_card.py
=======================
「局欲心變」框架分析卡的資料模型。

包含兩層：
1. Pydantic schemas — 用於 LLM 輸出解析、API 序列化、驗證
2. SQLAlchemy ORM model — 用於 PostgreSQL 持久化

設計原則：
- 欄位固定，不允許自由擴充（防止 LLM 幻覺導致 schema drift）
- 所有分析欄位都必須附帶 evidence_quotes（原文引用）
- confidence_score 強制 0.0–1.0，超出範圍 validator 拒絕
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MindShiftType(str, enum.Enum):
    """心態轉變的類型分類"""
    EMOTION = "emotion"          # 情緒轉變
    VALUES = "values"            # 價值觀轉變
    STRATEGY = "strategy"        # 策略轉變
    IDENTITY = "identity"        # 身份認知轉變
    STANCE = "stance"            # 立場轉換
    NONE = "none"                # 本場景無明顯心變


class FrameworkMatchLevel(str, enum.Enum):
    """框架符合程度（比 bool 更細緻）"""
    FULL = "full"                # 四個維度都齊備
    PARTIAL = "partial"          # 缺少 1–2 個維度
    WEAK = "weak"                # 有跡象但不明確
    NONE = "none"                # 此場景不適用該框架


# ---------------------------------------------------------------------------
# Pydantic Schemas (LLM 輸出 / API 傳輸)
# ---------------------------------------------------------------------------


class EvidenceQuote(BaseModel):
    """原文引用片段，強制要求每個分析都附帶證據"""
    text: str = Field(..., description="原文引用句，需完整摘自小說正文")
    chapter_hint: Optional[str] = Field(None, description="大略章節位置提示，如「第三章末段」")
    relevance: str = Field(..., description="此引用如何支持上方的分析判斷")


class SituationAnalysis(BaseModel):
    """局 — 外部局勢分析"""
    external_situation: str = Field(
        ...,
        description="此場景的外部局勢描述，需包含時間、地點、事件背景"
    )
    power_dynamics: str = Field(
        ...,
        description="場景中的權力關係，誰強誰弱，依據為何"
    )
    risks_and_constraints: str = Field(
        ...,
        description="場景中存在的風險、限制與邊界條件"
    )
    active_party: str = Field(
        ...,
        description="主動方：誰在推動局勢發展，採取行動"
    )
    passive_party: str = Field(
        ...,
        description="被動方：誰在被迫應對局勢，處於守勢"
    )
    resource_holders: str = Field(
        ...,
        description="資源持有者：誰掌握關鍵資訊、物資、人脈或話語權"
    )
    evidence_quotes: List[EvidenceQuote] = Field(
        ...,
        min_length=1,
        description="支持以上分析的原文引用，至少 1 條"
    )


class DesireAnalysis(BaseModel):
    """欲 — 欲望與動機分析"""
    explicit_desire: str = Field(
        ...,
        description="核心角色的顯性欲望：表面上想要什麼，對外表達的訴求"
    )
    implicit_desire: str = Field(
        ...,
        description="隱性欲望：未說出口或自己未意識到的真實渴望"
    )
    true_objective: str = Field(
        ...,
        description="真正目標：若顯性與隱性有差距，推斷最深層的驅動力"
    )
    desire_conflicts: str = Field(
        ...,
        description="欲望衝突：角色內心欲望之間，或與他人欲望之間的矛盾"
    )
    obstacles: str = Field(
        ...,
        description="阻礙：什麼因素阻止欲望被實現"
    )
    evidence_quotes: List[EvidenceQuote] = Field(
        ...,
        min_length=1,
        description="支持以上分析的原文引用，至少 1 條"
    )


class MindShiftAnalysis(BaseModel):
    """心變 — 心態轉變分析"""
    before_mindset: str = Field(
        ...,
        description="場景開始前的心態：角色進入此場景時抱持的信念、情緒或策略"
    )
    trigger_event: str = Field(
        ...,
        description="觸發轉變的具體事件或訊號：什麼打破了原有心態"
    )
    after_mindset: str = Field(
        ...,
        description="場景結束後的心態：轉變發生後角色的新信念、情緒或策略"
    )
    shift_type: MindShiftType = Field(
        ...,
        description="轉變類型分類"
    )
    shift_description: str = Field(
        ...,
        description="轉變的質性描述：從 X 到 Y，變化的幅度與意義"
    )
    is_reversible: bool = Field(
        ...,
        description="此次轉變是否可逆：True 表示角色未來可能回到原有心態"
    )
    evidence_quotes: List[EvidenceQuote] = Field(
        ...,
        min_length=1,
        description="支持以上分析的原文引用，至少 1 條"
    )


class FrameworkJudgment(BaseModel):
    """框架判定 — 「局欲心變」符合度評估"""
    match_level: FrameworkMatchLevel = Field(
        ...,
        description="整體符合程度"
    )
    matches_framework: bool = Field(
        ...,
        description="是否整體符合「局欲心變」框架（full 或 partial 為 True）"
    )
    reasoning: str = Field(
        ...,
        description="判定理由：為什麼符合或不符合，哪些維度強哪些弱"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="信心分數 0.0–1.0，反映分析的可靠程度"
    )
    missing_dimensions: List[str] = Field(
        default_factory=list,
        description="缺失或不明確的維度，如 ['implicit_desire', 'mind_shift']"
    )
    key_evidence_quotes: List[EvidenceQuote] = Field(
        ...,
        min_length=1,
        description="支持整體判定的最關鍵原文引用"
    )

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence_score 必須介於 0.0 與 1.0 之間，收到 {v}")
        return round(v, 4)

    @model_validator(mode="after")
    def sync_matches_framework(self) -> FrameworkJudgment:
        """確保 matches_framework 與 match_level 一致"""
        self.matches_framework = self.match_level in (
            FrameworkMatchLevel.FULL, FrameworkMatchLevel.PARTIAL
        )
        return self


class SceneFrameworkCardSchema(BaseModel):
    """
    完整的場景框架分析卡 Pydantic Schema。
    這是 LLM 必須輸出的頂層結構，也是 API 的傳輸格式。
    """
    card_id: Optional[str] = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="卡片唯一 ID"
    )
    scene_id: str = Field(..., description="對應的場景 ID")
    book_id: str = Field(..., description="所屬書籍 ID")
    chapter_number: int = Field(..., ge=1, description="章節編號")
    scene_number: int = Field(..., ge=1, description="場景在章節中的序號")

    # 核心角色（此場景分析的主體）
    focal_character: str = Field(
        ...,
        description="此場景分析聚焦的核心角色名稱"
    )
    secondary_characters: List[str] = Field(
        default_factory=list,
        description="場景中的其他重要角色"
    )

    # 四個分析維度
    situation: SituationAnalysis = Field(..., description="局：外部局勢分析")
    desire: DesireAnalysis = Field(..., description="欲：欲望與動機分析")
    mind_shift: MindShiftAnalysis = Field(..., description="心變：心態轉變分析")
    judgment: FrameworkJudgment = Field(..., description="框架判定")

    # 元資料
    model_used: str = Field(..., description="執行分析的 LLM 模型 ID")
    prompt_version: str = Field(..., description="使用的 prompt 版本號")
    analysis_version: str = Field(default="1.0.0", description="分析器版本")
    raw_llm_response: Optional[str] = Field(
        None,
        description="LLM 原始輸出，用於 debug 與重分析"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_human_reviewed: bool = Field(
        default=False,
        description="是否經過人工審閱與確認"
    )
    reviewer_notes: Optional[str] = Field(None, description="人工審閱備註")

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class SceneFrameworkCardUpdate(BaseModel):
    """用於人工修正部分欄位，不強制填完整卡"""
    situation: Optional[SituationAnalysis] = None
    desire: Optional[DesireAnalysis] = None
    mind_shift: Optional[MindShiftAnalysis] = None
    judgment: Optional[FrameworkJudgment] = None
    is_human_reviewed: Optional[bool] = None
    reviewer_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# SQLAlchemy ORM Model
# ---------------------------------------------------------------------------


class SceneFrameworkCard(Base):
    """
    PostgreSQL 持久化模型。
    四個分析維度以 JSONB 存儲，保留完整結構同時支援 GIN 索引查詢。
    """
    __tablename__ = "scene_framework_cards"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    scene_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scenes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_number: Mapped[int] = mapped_column(nullable=False)
    scene_number: Mapped[int] = mapped_column(nullable=False)

    focal_character: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    secondary_characters: Mapped[list] = mapped_column(JSON, default=list)

    # JSONB 欄位：存儲 Pydantic model 的 dict
    situation: Mapped[dict] = mapped_column(JSON, nullable=False)
    desire: Mapped[dict] = mapped_column(JSON, nullable=False)
    mind_shift: Mapped[dict] = mapped_column(JSON, nullable=False)
    judgment: Mapped[dict] = mapped_column(JSON, nullable=False)

    # 快速查詢欄位（從 judgment 冗餘提取，避免每次解包 JSON）
    match_level: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    mind_shift_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )

    # 元資料
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    raw_llm_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    scene: Mapped["Scene"] = relationship("Scene", back_populates="framework_card")  # type: ignore

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_schema(cls, card: SceneFrameworkCardSchema) -> "SceneFrameworkCard":
        """從 Pydantic schema 建立 ORM 物件"""
        return cls(
            id=card.card_id or str(uuid.uuid4()),
            scene_id=card.scene_id,
            book_id=card.book_id,
            chapter_number=card.chapter_number,
            scene_number=card.scene_number,
            focal_character=card.focal_character,
            secondary_characters=card.secondary_characters,
            situation=card.situation.model_dump(),
            desire=card.desire.model_dump(),
            mind_shift=card.mind_shift.model_dump(),
            judgment=card.judgment.model_dump(),
            # 冗餘快查欄位
            match_level=card.judgment.match_level,
            confidence_score=card.judgment.confidence_score,
            mind_shift_type=card.mind_shift.shift_type,
            model_used=card.model_used,
            prompt_version=card.prompt_version,
            analysis_version=card.analysis_version,
            raw_llm_response=card.raw_llm_response,
            is_human_reviewed=card.is_human_reviewed,
            reviewer_notes=card.reviewer_notes,
        )

    def to_schema(self) -> SceneFrameworkCardSchema:
        """轉換回 Pydantic schema"""
        return SceneFrameworkCardSchema(
            card_id=self.id,
            scene_id=self.scene_id,
            book_id=self.book_id,
            chapter_number=self.chapter_number,
            scene_number=self.scene_number,
            focal_character=self.focal_character,
            secondary_characters=self.secondary_characters,
            situation=SituationAnalysis(**self.situation),
            desire=DesireAnalysis(**self.desire),
            mind_shift=MindShiftAnalysis(**self.mind_shift),
            judgment=FrameworkJudgment(**self.judgment),
            model_used=self.model_used,
            prompt_version=self.prompt_version,
            analysis_version=self.analysis_version,
            raw_llm_response=self.raw_llm_response,
            created_at=self.created_at,
            is_human_reviewed=self.is_human_reviewed,
            reviewer_notes=self.reviewer_notes,
        )

    def __repr__(self) -> str:
        return (
            f"<SceneFrameworkCard scene={self.scene_id} "
            f"char={self.focal_character} "
            f"match={self.match_level} "
            f"conf={self.confidence_score:.2f}>"
        )

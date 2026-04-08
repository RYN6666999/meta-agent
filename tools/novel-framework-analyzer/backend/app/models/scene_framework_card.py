"""
scene_framework_card.py — 局心欲變分析卡資料模型（SQLite 版）
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MindShiftType(str, enum.Enum):
    EMOTION  = "emotion"
    VALUES   = "values"
    STRATEGY = "strategy"
    IDENTITY = "identity"
    STANCE   = "stance"
    NONE     = "none"

class FrameworkMatchLevel(str, enum.Enum):
    FULL    = "full"
    PARTIAL = "partial"
    WEAK    = "weak"
    NONE    = "none"

class SceneType(str, enum.Enum):
    FICTION_NARRATIVE    = "fiction_narrative"
    NONFICTION_CASE      = "nonfiction_case"
    NONFICTION_ARGUMENT  = "nonfiction_argument"

class LlmStatus(str, enum.Enum):
    PENDING = "pending"
    DONE    = "done"
    FAILED  = "failed"


# ---------------------------------------------------------------------------
# MVP 最小 Pydantic schema（LLM 輸出 → 儲存的正式合約）
# ---------------------------------------------------------------------------

class MvpSceneCard(BaseModel):
    """
    MVP 場景分析卡。LLM 輸出這個結構，analyzer 驗證後存 DB。

    四個維度（局/心/欲/變）為純文字；引用為字串陣列。
    延後欄位（confidence_score、match_level、mind_shift_type 等）不在此 schema 中。
    """
    book_id: str
    chapter_index: int
    scene_index: int

    summary: str
    characters: List[str] = Field(..., min_length=1)

    is_negotiation: bool = False
    negotiation_pattern_tags: List[str] = Field(default_factory=list)

    # 局心欲變四維（純文字）
    situation: str
    mind: str
    desire: str
    change: str

    change_intensity: int = Field(default=3, ge=1, le=5)
    quotes: List[str] = Field(default_factory=list)  # 原文引用（至少一條）

    model_used: str = ""
    prompt_version: str = "mvp-1"

    reviewed: bool = False
    llm_status: LlmStatus = LlmStatus.DONE

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# DEFERRED (Phase 2) — 以下 Pydantic schemas 在第一本書驗證後才啟用
# ---------------------------------------------------------------------------

class EvidenceQuote(BaseModel):
    text: str
    chapter_hint: Optional[str] = None
    relevance: str

class SituationAnalysis(BaseModel):
    external_situation: str
    power_dynamics: str
    risks_and_constraints: str
    active_party: str
    passive_party: str
    resource_holders: str
    macro_context: Optional[str] = None  # nonfiction: 作者用此案例論證什麼
    evidence_quotes: List[EvidenceQuote] = Field(..., min_length=1)

class DesireAnalysis(BaseModel):
    explicit_desire: str
    implicit_desire: str
    true_objective: str
    desire_conflicts: str
    obstacles: str
    evidence_quotes: List[EvidenceQuote] = Field(..., min_length=1)

class MindShiftAnalysis(BaseModel):
    before_mindset: str
    trigger_event: str
    after_mindset: str
    shift_type: MindShiftType
    shift_intensity: int = Field(default=3, ge=1, le=5)  # 強度 1-5，與類型分離
    shift_description: str
    is_reversible: bool
    shift_subject_level: Optional[str] = None  # individual / system / epistemic
    evidence_quotes: List[EvidenceQuote] = Field(..., min_length=1)

class FrameworkJudgment(BaseModel):
    match_level: FrameworkMatchLevel
    matches_framework: bool
    reasoning: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    missing_dimensions: List[str] = Field(default_factory=list)
    key_evidence_quotes: List[EvidenceQuote] = Field(..., min_length=1)

    @field_validator("confidence_score")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 4)

    @model_validator(mode="after")
    def sync_matches(self) -> FrameworkJudgment:
        self.matches_framework = self.match_level in (
            FrameworkMatchLevel.FULL, FrameworkMatchLevel.PARTIAL
        )
        return self

class SceneFrameworkCardSchema(BaseModel):
    card_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scene_id: str
    book_id: str
    chapter_number: int
    scene_number: int
    focal_character: str
    secondary_characters: List[str] = Field(default_factory=list)
    scene_type: SceneType = SceneType.FICTION_NARRATIVE
    insufficient_context: bool = False
    name_unresolved: bool = False
    is_negotiation_scene: bool = False
    negotiation_pattern_tags: List[str] = Field(default_factory=list)
    scene_labels: List[str] = Field(default_factory=list)  # decision / negotiation / confrontation / revelation
    situation: SituationAnalysis
    desire: DesireAnalysis
    mind_shift: MindShiftAnalysis
    judgment: FrameworkJudgment
    model_used: str
    prompt_version: str
    analysis_version: str = "1.0.0"
    raw_llm_response: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_human_reviewed: bool = False
    reviewer_notes: Optional[str] = None

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# SQLAlchemy ORM（SQLite 相容）
# ---------------------------------------------------------------------------

class SceneFrameworkCard(Base):
    __tablename__ = "scene_framework_cards"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True,
                                               default=lambda: str(uuid.uuid4()))
    scene_id: Mapped[str]      = mapped_column(String(36), nullable=False, index=True)
    book_id: Mapped[str]       = mapped_column(String(36), nullable=False, index=True)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    scene_number: Mapped[int]  = mapped_column(Integer, nullable=False)
    scene_text: Mapped[str]    = mapped_column(Text, nullable=False)

    focal_character: Mapped[str]       = mapped_column(String(100), nullable=False, index=True)
    secondary_characters: Mapped[list] = mapped_column(JSON, default=list)
    scene_type: Mapped[str]            = mapped_column(String(30), default="fiction_narrative", nullable=False, index=True)
    insufficient_context: Mapped[bool] = mapped_column(Boolean, default=False)
    name_unresolved: Mapped[bool]      = mapped_column(Boolean, default=False)
    is_negotiation_scene: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # MVP 欄位（2026-04 新增）
    summary:    Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_status: Mapped[str]           = mapped_column(String(20), default="done", nullable=False)
    negotiation_pattern_tags: Mapped[list] = mapped_column(JSON, default=list)
    scene_labels: Mapped[list] = mapped_column(JSON, default=list)

    situation:  Mapped[dict] = mapped_column(JSON, nullable=False)
    desire:     Mapped[dict] = mapped_column(JSON, nullable=False)
    mind_shift: Mapped[dict] = mapped_column(JSON, nullable=False)
    judgment:   Mapped[dict] = mapped_column(JSON, nullable=False)

    match_level:      Mapped[str]   = mapped_column(String(20), nullable=False, index=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    mind_shift_type:  Mapped[str]   = mapped_column(String(30), nullable=False, index=True)
    mind_shift_intensity: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    model_used:       Mapped[str]  = mapped_column(String(100), nullable=False)
    prompt_version:   Mapped[str]  = mapped_column(String(20), nullable=False)
    analysis_version: Mapped[str]  = mapped_column(String(20), default="1.0.0")
    raw_llm_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_notes:   Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @classmethod
    def from_schema(cls, card: SceneFrameworkCardSchema, scene_text: str = "") -> "SceneFrameworkCard":
        def enum_val(v):
            return v.value if hasattr(v, "value") else v
        return cls(
            id=card.card_id,
            scene_id=card.scene_id,
            book_id=card.book_id,
            chapter_number=card.chapter_number,
            scene_number=card.scene_number,
            scene_text=scene_text,
            focal_character=card.focal_character,
            secondary_characters=card.secondary_characters,
            scene_type=enum_val(card.scene_type),
            insufficient_context=card.insufficient_context,
            name_unresolved=card.name_unresolved,
            is_negotiation_scene=card.is_negotiation_scene,
            negotiation_pattern_tags=card.negotiation_pattern_tags,
            scene_labels=card.scene_labels,
            situation=card.situation.model_dump(),
            desire=card.desire.model_dump(),
            mind_shift=card.mind_shift.model_dump(),
            judgment=card.judgment.model_dump(),
            match_level=enum_val(card.judgment.match_level),
            confidence_score=card.judgment.confidence_score,
            mind_shift_type=enum_val(card.mind_shift.shift_type),
            mind_shift_intensity=card.mind_shift.shift_intensity,
            model_used=card.model_used,
            prompt_version=card.prompt_version,
            analysis_version=card.analysis_version,
            raw_llm_response=card.raw_llm_response,
        )

    @classmethod
    def from_mvp_card(cls, card: MvpSceneCard, raw_text: str = "") -> "SceneFrameworkCard":
        """從 MVP schema 建立 ORM 物件。"""
        focal = card.characters[0] if card.characters else ""
        secondary = card.characters[1:] if len(card.characters) > 1 else []
        return cls(
            id=str(uuid.uuid4()),
            scene_id=f"{card.book_id}_ch{card.chapter_index}_s{card.scene_index}",
            book_id=card.book_id,
            chapter_number=card.chapter_index,
            scene_number=card.scene_index,
            scene_text=raw_text,
            summary=card.summary,
            focal_character=focal,
            secondary_characters=secondary,
            scene_type="fiction_narrative",
            is_negotiation_scene=card.is_negotiation,
            negotiation_pattern_tags=card.negotiation_pattern_tags,
            scene_labels=[],
            situation={"text": card.situation},
            desire={"text": card.desire},
            mind_shift={"text": card.mind, "change": card.change,
                        "change_intensity": card.change_intensity},
            judgment={"quotes": card.quotes},
            match_level="none",          # deferred
            confidence_score=0.0,        # deferred
            mind_shift_type="none",      # deferred
            mind_shift_intensity=card.change_intensity,
            model_used=card.model_used,
            prompt_version=card.prompt_version,
            llm_status=card.llm_status if isinstance(card.llm_status, str)
                        else card.llm_status.value,
        )

    def to_mvp(self) -> dict:
        """返回 MVP 視角的欄位字典（供 API 序列化使用）。"""
        def _text(blob) -> str:
            if isinstance(blob, dict):
                return blob.get("text") or blob.get("external_situation") or ""
            return ""
        ms = self.mind_shift or {}
        return {
            "book_id": self.book_id,
            "chapter_index": self.chapter_number,
            "scene_index": self.scene_number,
            "summary": self.summary or "",
            "characters": ([self.focal_character] + (self.secondary_characters or [])),
            "is_negotiation": bool(self.is_negotiation_scene),
            "negotiation_pattern_tags": self.negotiation_pattern_tags or [],
            "situation": _text(self.situation),
            "mind": _text(ms) if not ms.get("change") else ms.get("text", ""),
            "desire": _text(self.desire),
            "change": ms.get("change", ""),
            "change_intensity": ms.get("change_intensity", self.mind_shift_intensity or 3),
            "quotes": (self.judgment or {}).get("quotes", []),
            "reviewed": bool(self.is_human_reviewed),
            "llm_status": self.llm_status or "done",
            "model_used": self.model_used or "",
            "prompt_version": self.prompt_version or "",
        }

    def __repr__(self):
        return (f"<Card ch={self.chapter_number} s={self.scene_number} "
                f"char={self.focal_character} match={self.match_level} "
                f"conf={self.confidence_score:.2f}>")

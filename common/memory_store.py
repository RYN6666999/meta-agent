"""
common/memory_store.py — Phase 1 結構化記憶層

提供：
  MemoryRecord   — Pydantic model（Phase 1 主真相層記憶記錄）
  init_db()      — 建立 SQLite table + indexes（idempotent）
  record_to_row() — MemoryRecord → tuple（用於 INSERT）
  row_to_record() — sqlite3.Row → MemoryRecord（用於 SELECT）

不包含：retrieval / writeback / correction / dedup
這些由後續 TODO 在此模組上疊加。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from common.config import STRUCTURED_MEMORY_DB

# ── 型別別名 ──────────────────────────────────────────────────────────

MemoryType = Literal[
    "fact_memory",
    "preference_memory",
    "episode_memory",
    "task_memory",
]

SourceType = Literal[
    "user_said",
    "tool_observed",
    "system_inferred",
    "imported_record",
]

FreshnessState = Literal["fresh", "stale", "expired"]
LifecycleStatus = Literal["active", "deleted", "archived"]
SubjectType = Literal["user", "agent", "task", "org"]


# ── Sub-models ────────────────────────────────────────────────────────

class SubjectRef(BaseModel):
    """單一 identity 參照。subject_refs 永遠是 list，至少含一個。"""
    type: SubjectType
    id: str
    namespace: str = "default"


class SourceInfo(BaseModel):
    """記憶來源。source_type 必填，不允許缺失。"""
    source_type: SourceType
    source_ref: str = ""        # e.g. conversation message ID
    captured_at: datetime = Field(default_factory=datetime.utcnow)


class QualityInfo(BaseModel):
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    freshness_state: FreshnessState = "fresh"


class LifecycleInfo(BaseModel):
    status: LifecycleStatus = "active"
    supersedes: Optional[str] = None    # memory_id of the superseded record
    expires_at: Optional[datetime] = None


# ── 主記錄 ────────────────────────────────────────────────────────────

class MemoryRecord(BaseModel):
    """
    Phase 1 商用級外掛大腦的最小記憶記錄。

    - memory_id:    全域唯一，自動生成
    - memory_type:  四種之一（fact / preference / episode / task）
    - subject_refs: 至少一個 SubjectRef，決定此記憶屬於誰
    - source:       來源必填，source_type 不得缺失
    - quality:      重要性 / 置信度 / 新鮮度
    - lifecycle:    狀態 / 取代關係 / 過期時間
    - created_at / updated_at: audit 欄位
    """
    memory_id: str = Field(
        default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}"
    )
    memory_type: MemoryType
    subject_refs: list[SubjectRef] = Field(min_length=1)
    title: str = ""
    content: str
    source: SourceInfo
    quality: QualityInfo = Field(default_factory=QualityInfo)
    lifecycle: LifecycleInfo = Field(default_factory=LifecycleInfo)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── SQLite schema ─────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS memory_records (
    memory_id       TEXT PRIMARY KEY,
    memory_type     TEXT NOT NULL,
    subject_refs    TEXT NOT NULL,
    namespace       TEXT NOT NULL DEFAULT 'default',
    title           TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    source_ref      TEXT NOT NULL DEFAULT '',
    captured_at     TEXT NOT NULL,
    importance      REAL NOT NULL DEFAULT 0.5,
    confidence      REAL NOT NULL DEFAULT 0.8,
    freshness_state TEXT NOT NULL DEFAULT 'fresh',
    status          TEXT NOT NULL DEFAULT 'active',
    supersedes      TEXT,
    expires_at      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_mem_type    ON memory_records(memory_type)",
    "CREATE INDEX IF NOT EXISTS idx_status      ON memory_records(status)",
    "CREATE INDEX IF NOT EXISTS idx_source_type ON memory_records(source_type)",
    "CREATE INDEX IF NOT EXISTS idx_namespace   ON memory_records(namespace)",
    "CREATE INDEX IF NOT EXISTS idx_created_at  ON memory_records(created_at)",
]


def init_db(db_path: str | None = None) -> None:
    """
    建立 SQLite table 與 indexes（idempotent，可安全重複呼叫）。

    Args:
        db_path: 覆寫預設路徑（測試用）；None 則使用 config.STRUCTURED_MEMORY_DB
    """
    path = db_path or str(STRUCTURED_MEMORY_DB)
    with sqlite3.connect(path) as conn:
        conn.execute(_CREATE_TABLE)
        for stmt in _CREATE_INDEXES:
            conn.execute(stmt)
        conn.commit()


# ── 序列化工具 ────────────────────────────────────────────────────────

def _dt_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _primary_namespace(record: MemoryRecord) -> str:
    """
    從 subject_refs 中取出第一個非 'default' namespace；
    若全為 default 則回傳 'default'。
    用於 namespace 欄位的快速過濾索引。
    """
    for ref in record.subject_refs:
        if ref.namespace != "default":
            return ref.namespace
    return "default"


def record_to_row(record: MemoryRecord) -> tuple:
    """
    MemoryRecord → SQLite INSERT tuple。

    tuple 欄位順序對應 INSERT INTO memory_records VALUES (?, ?, ...)
    """
    return (
        record.memory_id,
        record.memory_type,
        json.dumps([ref.model_dump() for ref in record.subject_refs], ensure_ascii=False),
        _primary_namespace(record),
        record.title,
        record.content,
        record.source.source_type,
        record.source.source_ref,
        _dt_str(record.source.captured_at),
        record.quality.importance,
        record.quality.confidence,
        record.quality.freshness_state,
        record.lifecycle.status,
        record.lifecycle.supersedes,
        _dt_str(record.lifecycle.expires_at),
        _dt_str(record.created_at),
        _dt_str(record.updated_at),
    )


def row_to_record(row: sqlite3.Row | tuple) -> MemoryRecord:
    """
    sqlite3.Row（或等長 tuple）→ MemoryRecord。

    欄位順序與 record_to_row 一致。
    """
    (
        memory_id,
        memory_type,
        subject_refs_json,
        namespace,      # noqa: F841 — kept for clarity; embedded in subject_refs
        title,
        content,
        source_type,
        source_ref,
        captured_at_str,
        importance,
        confidence,
        freshness_state,
        status,
        supersedes,
        expires_at_str,
        created_at_str,
        updated_at_str,
    ) = row

    subject_refs = [SubjectRef(**item) for item in json.loads(subject_refs_json)]

    return MemoryRecord(
        memory_id=memory_id,
        memory_type=memory_type,
        subject_refs=subject_refs,
        title=title or "",
        content=content,
        source=SourceInfo(
            source_type=source_type,
            source_ref=source_ref or "",
            captured_at=datetime.fromisoformat(captured_at_str),
        ),
        quality=QualityInfo(
            importance=float(importance),
            confidence=float(confidence),
            freshness_state=freshness_state,
        ),
        lifecycle=LifecycleInfo(
            status=status,
            supersedes=supersedes,
            expires_at=datetime.fromisoformat(expires_at_str) if expires_at_str else None,
        ),
        created_at=datetime.fromisoformat(created_at_str),
        updated_at=datetime.fromisoformat(updated_at_str),
    )

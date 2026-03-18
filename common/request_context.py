"""Unified request context for all decision points."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class RequestContext:
    """
    統一決策入口：所有 memory 操作都帶著這個 context，
    確保 scope 判定與狀態檢查一致。
    """
    user_id: str
    scope: Literal["global", "persona"] = field(init=False)
    trigger_checkpoints: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """一次性判定：user_id 決定 scope"""
        self.scope = "persona" if self.user_id != "default" else "global"

    def __repr__(self) -> str:
        return f"RequestContext(user_id={self.user_id!r}, scope={self.scope!r}, checkpoints={self.trigger_checkpoints!r})"

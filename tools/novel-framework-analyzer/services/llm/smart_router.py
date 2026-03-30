"""
smart_router.py — 智慧路由分析器

依照 focal_character 決定用哪個 LLM：
  - priority_chars（預設：寧凡）→ haiku_analyzer（高品質）
  - 其他角色               → free_analyzer （省錢）

典型節省：若 65% 場景是寧凡，35% 是其他 → 省約 30–35% 費用
"""
from __future__ import annotations

from typing import List

from backend.app.services.framework_analyzer import AnalysisContext, AnalysisResult, FrameworkAnalyzer


class SmartRouter:
    """
    per-scene 路由：priority 角色用 haiku，其他用 free model。

    Args:
        haiku_analyzer:   高品質分析器（Haiku / Sonnet）
        free_analyzer:    免費模型分析器
        priority_chars:   需要高品質的角色名單，預設 ["寧凡"]
    """

    def __init__(
        self,
        haiku_analyzer: FrameworkAnalyzer,
        free_analyzer:  FrameworkAnalyzer,
        priority_chars: List[str] | None = None,
    ):
        self.haiku  = haiku_analyzer
        self.free   = free_analyzer
        self.priority = set(priority_chars or ["寧凡"])
        self._haiku_count = 0
        self._free_count  = 0

    def _route(self, ctx: AnalysisContext) -> tuple[FrameworkAnalyzer, str]:
        """返回 (analyzer, label)"""
        if ctx.focal_character in self.priority:
            return self.haiku, "haiku"
        return self.free, "free"

    async def analyze(self, ctx: AnalysisContext) -> AnalysisResult:
        analyzer, label = self._route(ctx)
        if label == "haiku":
            self._haiku_count += 1
        else:
            self._free_count += 1
        return await analyzer.analyze(ctx)

    @property
    def stats(self) -> dict:
        total = self._haiku_count + self._free_count
        return {
            "haiku_scenes": self._haiku_count,
            "free_scenes":  self._free_count,
            "total":        total,
            "haiku_pct":    round(self._haiku_count / total * 100, 1) if total else 0,
        }

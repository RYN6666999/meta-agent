"""
hybrid_router.py
================
HybridAnalyzer — 折衷方案：本地 Stage1 篩選 + 雲端 Stage2+3 分析

成本結構：
  Stage1 (Ollama)   : 0 元，本地跑，只要 150 tokens 輸出
  Stage2+3 (Haiku)  : ~0.001 USD / 場景（2000 tokens 估計）

效果：
  - 約 15-25% 場景在 Stage1 被篩除（純過渡場景），完全不花 API
  - 其餘場景由 Haiku 高品質完成，3-8 秒出結果
  - 本地等待只有 Stage1 的 ~45 秒，可以接受

使用：
  python3 scripts/batch_analyze.py --chapters 1-10 --mode hybrid
  python3 scripts/batch_analyze.py --chapters 1-10 --mode free   (OpenRouter 免費模型)
  python3 scripts/batch_analyze.py --chapters 1-10 --mode haiku  (純付費，最快最穩)
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from backend.app.services.framework_analyzer import (
    AbstractLLMClient, AnalysisContext, AnalysisError, AnalysisResult,
    FrameworkAnalyzer, LLMMessage,
)
from backend.app.services.msa_analyzer import (
    MSAAnalyzer, Stage1Result, _S1_SYSTEM, _S1_USER,
)

logger = logging.getLogger(__name__)


class HybridAnalyzer:
    """
    Stage1 用本地 Ollama（免費），Stage2+3 用 OpenRouter（付費/免費）。

    Args:
        local_client:  OllamaClient，只跑 Stage1 篩選
        cloud_client:  OpenRouterClient，跑 Stage2+3 完整分析
        prompt_dir:    prompts 目錄
    """

    def __init__(
        self,
        local_client: AbstractLLMClient,
        cloud_client: AbstractLLMClient,
        prompt_dir: str,
    ) -> None:
        self.local = local_client
        self.cloud = cloud_client
        self._full_analyzer = FrameworkAnalyzer(
            llm_client=cloud_client,
            prompt_dir=prompt_dir,
        )
        self._local_msa = MSAAnalyzer(llm_client=local_client)

    async def analyze(self, ctx: AnalysisContext) -> AnalysisResult:
        """
        Stage1: 本地快速篩選
        → 若 worthy=False: 返回 skipped card（不花 API）
        → 若 worthy=True:  雲端完整分析
        """
        total_tokens = 0

        # ── Stage1：本地篩選 ──
        try:
            s1 = await self._local_stage1(ctx)
            total_tokens += s1.tokens_used
            logger.debug(f"[Hybrid] S1 local: worthy={s1.worthy} char={s1.focal_character}")
        except Exception as e:
            logger.warning(f"[Hybrid] Stage1 local failed ({e})，fallback 全部轉雲端")
            s1 = Stage1Result(worthy=True, focal_character=ctx.focal_character,
                              complexity=3, tokens_used=0)

        if not s1.worthy:
            logger.info(f"[Hybrid] 場景 {ctx.scene_id} Stage1 篩除（本地），0 API cost")
            card = self._local_msa._make_skipped_card(ctx, s1)
            return AnalysisResult(card=card, retry_count=0, total_tokens=total_tokens)

        # 更新 focal_character
        if s1.focal_character and s1.focal_character != ctx.focal_character:
            ctx = AnalysisContext(
                scene_id=ctx.scene_id,
                book_id=ctx.book_id,
                scene_text=ctx.scene_text,
                chapter_number=ctx.chapter_number,
                scene_number=ctx.scene_number,
                focal_character=s1.focal_character,
                known_characters=ctx.known_characters,
                preceding_context=ctx.preceding_context,
                book_title=ctx.book_title,
            )

        # ── Stage2+3：雲端完整分析 ──
        result = await self._full_analyzer.analyze(ctx)
        result.total_tokens += total_tokens
        return result

    async def _local_stage1(self, ctx: AnalysisContext) -> Stage1Result:
        """在本地跑 Stage1 篩選"""
        preview = ctx.scene_text[:300]
        user_msg = _S1_USER.replace("{preview}", preview)
        resp = await self.local.complete(
            [LLMMessage(role="system", content=_S1_SYSTEM),
             LLMMessage(role="user",   content=user_msg)],
            temperature=0.1,
            max_tokens=120,
        )
        raw = resp.content.strip()
        # 去除可能的 markdown 包裹
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        try:
            data = json.loads(raw)
            return Stage1Result(
                worthy=bool(data.get("worthy", True)),
                focal_character=str(data.get("focal_character", ctx.focal_character)),
                complexity=int(data.get("complexity", 3)),
                skip_reason=str(data.get("skip_reason", "")),
                tokens_used=resp.input_tokens + resp.output_tokens,
            )
        except Exception as e:
            logger.warning(f"Stage1 JSON 解析失敗，預設通過：{e}\n原始：{raw[:100]}")
            return Stage1Result(
                worthy=True,
                focal_character=ctx.focal_character,
                complexity=3,
                tokens_used=resp.input_tokens + resp.output_tokens,
            )

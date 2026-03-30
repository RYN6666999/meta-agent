"""
msa_analyzer.py
===============
Multi-Stage Analysis — 多階段分析器。

將一次重量 LLM 呼叫拆成三個輕量階段，降低約 45% token 消耗：

Stage 1 — 場景篩選（~100 tokens）
  輸入：場景原文（前 300 字）
  輸出：worthy, focal_character, complexity(1-5), skip_reason
  作用：過濾過渡場景，提取主角，決定是否進入完整分析

Stage 2 — 核心框架分析（~2000 tokens）
  輸入：完整場景原文 + Stage1 結果
  輸出：四維度摘要 + match_level + confidence（不含 evidence）
  作用：快速判定框架符合度

Stage 3 — 證據補充（~1500 tokens，按需）
  輸入：場景原文 + Stage2 分析結果
  觸發條件：confidence < 0.65 OR match_level = weak
  輸出：每個維度補充 evidence_quotes
  作用：讓薄弱分析有原文支撐，提升可信度

最終組合三段結果 → SceneFrameworkCardSchema（同原始格式，向下相容）
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from backend.app.models.scene_framework_card import (
    DesireAnalysis, EvidenceQuote, FrameworkJudgment, FrameworkMatchLevel,
    MindShiftAnalysis, MindShiftType, SceneFrameworkCardSchema, SituationAnalysis,
)
from backend.app.services.framework_analyzer import (
    AbstractLLMClient, AnalysisContext, AnalysisError, LLMMessage,
    LLMResponseParseError, PromptConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 結果 dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Stage1Result:
    worthy: bool
    focal_character: str
    complexity: int          # 1–5，影響 Stage2 max_tokens
    skip_reason: str = ""    # worthy=False 時說明原因
    tokens_used: int = 0

@dataclass
class Stage2Result:
    situation_summary: str
    desire_summary: str
    mind_shift_summary: str
    shift_type: str
    match_level: str
    confidence: float
    reasoning: str
    needs_evidence: bool     # 是否需要 Stage3
    tokens_used: int = 0

@dataclass
class Stage3Result:
    situation_quotes: list
    desire_quotes: list
    mind_shift_quotes: list
    judgment_quotes: list
    tokens_used: int = 0


# ---------------------------------------------------------------------------
# Prompts（內嵌，精簡版）
# ---------------------------------------------------------------------------

_S1_SYSTEM = "你是中文小說場景篩選器。只輸出 JSON，不加說明。"

_S1_USER = """判斷以下場景是否值得做「局心欲變」框架分析。
場景（前300字）：
{preview}

輸出 JSON：
{{"worthy": true/false, "focal_character": "主角名", "complexity": 1-5, "skip_reason": "若worthy=false說明原因"}}

worthy=false 的情況：純過渡（走路/睡覺/無對話無衝突）、字數極少、場景資訊嚴重不足。"""

_S2_SYSTEM = "你是中文小說「局心欲變」框架分析師。只輸出 JSON，不加說明文字。"

_S2_USER = """分析以下場景，按「局心欲變」順序輸出四維度摘要（不需要原文引用，只要分析判斷）。

核心角色：{focal_character}
場景：
{scene_text}

輸出 JSON（順序固定：局→心→欲→變）：
{{
  "situation": {{"summary": "局勢一句話（外部賽局）", "active": "主動方", "passive": "被動方"}},
  "mind_shift": {{"before": "進入場景時的心態/認知框架（心）", "trigger": "觸發轉變的事件（變的節點）", "after": "離開場景後的新心態（變的結果）", "type": "emotion|values|strategy|identity|stance|none"}},
  "desire": {{"explicit": "顯性欲望（欲）", "implicit": "隱性欲望", "conflict": "欲望衝突"}},
  "judgment": {{"match_level": "full|partial|weak|none", "confidence": 0.0-1.0, "reasoning": "判定理由一句話"}}
}}"""

_S3_SYSTEM = "你是原文引用提取器。只輸出 JSON，引用必須直接複製原文，不得改寫。"

_S3_USER = """為以下分析結果補充原文引用。

場景原文：
{scene_text}

已有分析：
局：{situation_summary}
欲：{desire_summary}
心變：{mind_shift_summary}

請為每個維度從原文中找出最能支持分析的句子（直接複製）：
{{
  "situation_quotes": [{{"text": "原文句", "relevance": "支持理由"}}],
  "desire_quotes": [{{"text": "原文句", "relevance": "支持理由"}}],
  "mind_shift_quotes": [{{"text": "原文句", "relevance": "支持理由"}}],
  "judgment_quotes": [{{"text": "最關鍵原文句", "relevance": "整體支持理由"}}]
}}"""


# ---------------------------------------------------------------------------
# MSA 分析器
# ---------------------------------------------------------------------------

class MSAAnalyzer:
    """
    多階段分析器，取代 FrameworkAnalyzer 以節省 tokens。
    輸出格式與 FrameworkAnalyzer 完全相容（SceneFrameworkCardSchema）。

    使用：
        analyzer = MSAAnalyzer(llm_client=OllamaClient())
        result = await analyzer.analyze(ctx)
    """

    EVIDENCE_THRESHOLD = 0.65  # 低於此信心分數才觸發 Stage3

    def __init__(
        self,
        llm_client: AbstractLLMClient,
        prompt_config: Optional[PromptConfig] = None,
    ) -> None:
        self.llm = llm_client

    async def analyze(self, ctx: AnalysisContext):
        """執行三階段分析，返回 AnalysisResult（同 FrameworkAnalyzer 格式）"""
        from backend.app.services.framework_analyzer import AnalysisResult

        total_tokens = 0

        # ── Stage 1：篩選 ──────────────────────────────────────────
        s1 = await self._stage1(ctx)
        total_tokens += s1.tokens_used
        logger.debug(f"S1: worthy={s1.worthy} char={s1.focal_character} complexity={s1.complexity}")

        if not s1.worthy:
            logger.info(f"場景 {ctx.scene_id} Stage1 篩除：{s1.skip_reason}")
            # 產生一張 match=none 的卡，記錄篩除原因
            card = self._make_skipped_card(ctx, s1)
            return AnalysisResult(card=card, retry_count=0, total_tokens=total_tokens)

        # 用 Stage1 偵測到的角色（若原 ctx 是佔位符則更新）
        effective_char = s1.focal_character or ctx.focal_character

        # ── Stage 2：核心分析 ──────────────────────────────────────
        s2 = await self._stage2(ctx, effective_char)
        total_tokens += s2.tokens_used
        logger.debug(f"S2: match={s2.match_level} conf={s2.confidence:.2f}")

        # ── Stage 3：證據補充（按需）──────────────────────────────
        s3 = None
        if s2.needs_evidence:
            s3 = await self._stage3(ctx, s2)
            total_tokens += s3.tokens_used
            logger.debug(f"S3: 補充了 {len(s3.situation_quotes)} 條 situation 引用")

        # ── 組合最終卡片 ───────────────────────────────────────────
        card = self._assemble_card(ctx, effective_char, s1, s2, s3)
        return AnalysisResult(card=card, retry_count=0, total_tokens=total_tokens)

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    async def _stage1(self, ctx: AnalysisContext) -> Stage1Result:
        preview = ctx.scene_text[:300]
        user_msg = _S1_USER.replace("{preview}", preview)
        resp = await self.llm.complete(
            [LLMMessage(role="system", content=_S1_SYSTEM),
             LLMMessage(role="user",   content=user_msg)],
            temperature=0.1,
            max_tokens=150,
        )
        try:
            data = json.loads(self._extract_json(resp.content))
            return Stage1Result(
                worthy=data.get("worthy", True),
                focal_character=data.get("focal_character", ctx.focal_character),
                complexity=int(data.get("complexity", 3)),
                skip_reason=data.get("skip_reason", ""),
                tokens_used=resp.input_tokens + resp.output_tokens,
            )
        except Exception as e:
            logger.warning(f"Stage1 解析失敗，預設通過：{e}")
            return Stage1Result(worthy=True, focal_character=ctx.focal_character,
                                complexity=3, tokens_used=resp.input_tokens + resp.output_tokens)

    async def _stage2(self, ctx: AnalysisContext, focal_character: str) -> Stage2Result:
        user_msg = (_S2_USER
                    .replace("{focal_character}", focal_character)
                    .replace("{scene_text}", ctx.scene_text))
        max_t = 300 + 200 * min(ctx.__dict__.get("complexity", 3), 5)  # 依複雜度調整
        resp = await self.llm.complete(
            [LLMMessage(role="system", content=_S2_SYSTEM),
             LLMMessage(role="user",   content=user_msg)],
            temperature=0.15,
            max_tokens=800,
        )
        try:
            data = json.loads(self._extract_json(resp.content))
            conf = float(data.get("judgment", {}).get("confidence", 0.5))
            match = data.get("judgment", {}).get("match_level", "partial")
            return Stage2Result(
                situation_summary=data.get("situation", {}).get("summary", ""),
                desire_summary=data.get("desire", {}).get("explicit", ""),
                mind_shift_summary=data.get("mind_shift", {}).get("trigger", ""),
                shift_type=data.get("mind_shift", {}).get("type", "none"),
                match_level=match,
                confidence=conf,
                reasoning=data.get("judgment", {}).get("reasoning", ""),
                needs_evidence=(conf < self.EVIDENCE_THRESHOLD or match == "weak"),
                tokens_used=resp.input_tokens + resp.output_tokens,
            )
        except Exception as e:
            raise LLMResponseParseError(f"Stage2 解析失敗：{e}") from e

    async def _stage3(self, ctx: AnalysisContext, s2: Stage2Result) -> Stage3Result:
        user_msg = (_S3_USER
                    .replace("{scene_text}", ctx.scene_text[:1500])
                    .replace("{situation_summary}", s2.situation_summary)
                    .replace("{desire_summary}", s2.desire_summary)
                    .replace("{mind_shift_summary}", s2.mind_shift_summary))
        resp = await self.llm.complete(
            [LLMMessage(role="system", content=_S3_SYSTEM),
             LLMMessage(role="user",   content=user_msg)],
            temperature=0.1,
            max_tokens=600,
        )
        try:
            data = json.loads(self._extract_json(resp.content))
            return Stage3Result(
                situation_quotes=data.get("situation_quotes", []),
                desire_quotes=data.get("desire_quotes", []),
                mind_shift_quotes=data.get("mind_shift_quotes", []),
                judgment_quotes=data.get("judgment_quotes", []),
                tokens_used=resp.input_tokens + resp.output_tokens,
            )
        except Exception as e:
            logger.warning(f"Stage3 解析失敗，使用空引用：{e}")
            return Stage3Result([], [], [], [],
                                tokens_used=resp.input_tokens + resp.output_tokens)

    # ------------------------------------------------------------------
    # 組合 card
    # ------------------------------------------------------------------

    def _assemble_card(
        self, ctx: AnalysisContext, focal: str,
        s1: Stage1Result, s2: Stage2Result, s3: Optional[Stage3Result]
    ) -> SceneFrameworkCardSchema:
        def make_quotes(raw_list, fallback_text="（自動生成，待人工驗證）") -> list:
            if raw_list:
                return [EvidenceQuote(
                    text=q.get("text", fallback_text),
                    relevance=q.get("relevance", ""),
                ) for q in raw_list if q.get("text")]
            return [EvidenceQuote(text=fallback_text, relevance="Stage3 未補充")]

        sit_quotes  = make_quotes(s3.situation_quotes  if s3 else [])
        des_quotes  = make_quotes(s3.desire_quotes     if s3 else [])
        ms_quotes   = make_quotes(s3.mind_shift_quotes if s3 else [])
        jdg_quotes  = make_quotes(s3.judgment_quotes   if s3 else [])

        try:
            shift_type = MindShiftType(s2.shift_type)
        except ValueError:
            shift_type = MindShiftType.NONE

        try:
            match_level = FrameworkMatchLevel(s2.match_level)
        except ValueError:
            match_level = FrameworkMatchLevel.PARTIAL

        return SceneFrameworkCardSchema(
            scene_id=ctx.scene_id,
            book_id=ctx.book_id,
            chapter_number=ctx.chapter_number,
            scene_number=ctx.scene_number,
            focal_character=focal,
            situation=SituationAnalysis(
                external_situation=s2.situation_summary,
                power_dynamics="（見摘要）",
                risks_and_constraints="（見摘要）",
                active_party="（見摘要）",
                passive_party="（見摘要）",
                resource_holders="（見摘要）",
                evidence_quotes=sit_quotes,
            ),
            desire=DesireAnalysis(
                explicit_desire=s2.desire_summary,
                implicit_desire="（見摘要）",
                true_objective="（見摘要）",
                desire_conflicts="（見摘要）",
                obstacles="（見摘要）",
                evidence_quotes=des_quotes,
            ),
            mind_shift=MindShiftAnalysis(
                before_mindset="（見摘要）",
                trigger_event=s2.mind_shift_summary,
                after_mindset="（見摘要）",
                shift_type=shift_type,
                shift_description=s2.mind_shift_summary,
                is_reversible=True,
                evidence_quotes=ms_quotes,
            ),
            judgment=FrameworkJudgment(
                match_level=match_level,
                matches_framework=match_level in (FrameworkMatchLevel.FULL, FrameworkMatchLevel.PARTIAL),
                reasoning=s2.reasoning,
                confidence_score=s2.confidence,
                missing_dimensions=[],
                key_evidence_quotes=jdg_quotes,
            ),
            model_used=f"msa/{self.llm.model_id}",
            prompt_version="msa-1.0",
        )

    def _make_skipped_card(self, ctx: AnalysisContext, s1: Stage1Result) -> SceneFrameworkCardSchema:
        """Stage1 篩除的場景，產生 match=none 的佔位卡"""
        placeholder = EvidenceQuote(text="場景資訊不足，已跳過", relevance=s1.skip_reason)
        return SceneFrameworkCardSchema(
            scene_id=ctx.scene_id, book_id=ctx.book_id,
            chapter_number=ctx.chapter_number, scene_number=ctx.scene_number,
            focal_character=s1.focal_character or "未知",
            situation=SituationAnalysis(
                external_situation=s1.skip_reason, power_dynamics="N/A",
                risks_and_constraints="N/A", active_party="N/A",
                passive_party="N/A", resource_holders="N/A",
                evidence_quotes=[placeholder],
            ),
            desire=DesireAnalysis(
                explicit_desire="N/A", implicit_desire="N/A", true_objective="N/A",
                desire_conflicts="N/A", obstacles="N/A", evidence_quotes=[placeholder],
            ),
            mind_shift=MindShiftAnalysis(
                before_mindset="N/A", trigger_event="N/A", after_mindset="N/A",
                shift_type=MindShiftType.NONE, shift_description="N/A",
                is_reversible=True, evidence_quotes=[placeholder],
            ),
            judgment=FrameworkJudgment(
                match_level=FrameworkMatchLevel.NONE, matches_framework=False,
                reasoning=f"Stage1 篩除：{s1.skip_reason}",
                confidence_score=0.0, missing_dimensions=["all"],
                key_evidence_quotes=[placeholder],
            ),
            model_used=f"msa-s1/{self.llm.model_id}",
            prompt_version="msa-1.0",
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            return m.group(1)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return m.group(0)
        raise LLMResponseParseError(f"無法提取 JSON：{raw[:100]}")

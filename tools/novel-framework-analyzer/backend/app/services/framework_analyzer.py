"""
framework_analyzer.py
======================
「局心欲變」框架分析器核心服務。

架構：
  AbstractLLMClient  ← 可替換 OpenAI / Anthropic / 本地模型
       ↓
  FrameworkAnalyzer  ← 主分析器：呼叫 LLM、解析輸出、驗證結果
       ↓
  SceneFrameworkCardSchema  ← 固定 schema 輸出

設計決策：
1. LLM 呼叫與解析邏輯分離：換模型不動業務邏輯
2. 三次 retry + structured output 強制解析
3. 所有分析都要求 evidence_quotes，無引用視為無效
4. 分析失敗返回 AnalysisError，不靜默吞噬
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.app.models.scene_framework_card import (
    DesireAnalysis,
    EvidenceQuote,
    FrameworkJudgment,
    FrameworkMatchLevel,
    MindShiftAnalysis,
    MindShiftType,
    SceneFrameworkCardSchema,
    SituationAnalysis,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AnalysisError(Exception):
    """框架分析失敗的基底例外"""


class LLMResponseParseError(AnalysisError):
    """LLM 輸出無法解析為合法 schema"""


class InsufficientEvidenceError(AnalysisError):
    """分析結果缺少原文引用"""


# ---------------------------------------------------------------------------
# LLM Adapter 抽象層（interface + adapter pattern）
# ---------------------------------------------------------------------------


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    raw: Any = None  # 保留原始 response 物件供 debug


class AbstractLLMClient(ABC):
    """
    所有 LLM 後端都必須實作此介面。
    換模型只需換 adapter，不改 FrameworkAnalyzer。
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:
        """呼叫 LLM 並返回 LLMResponse"""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """回傳此 adapter 使用的模型 ID，存入 card.model_used"""
        ...


# ---------------------------------------------------------------------------
# Prompt 載入
# ---------------------------------------------------------------------------


@dataclass
class PromptConfig:
    """Prompt 版本管理"""
    version: str
    system_prompt: str
    analysis_template: str  # 包含 {scene_text} 佔位符

    @classmethod
    def load(cls, prompt_dir: str = "prompts") -> "PromptConfig":
        """從 prompts/ 目錄載入，便於版本控制 prompt"""
        import os

        # system prompt：框架定義 + 輸出規則
        system_path = os.path.join(prompt_dir, "framework_analysis_prompt.txt")
        # user template：含 {scene_text} 佔位符
        user_path = os.path.join(prompt_dir, "framework_user_template.txt")

        try:
            with open(system_path, encoding="utf-8") as f:
                system_raw = f.read()
        except FileNotFoundError:
            system_raw = ""

        try:
            with open(user_path, encoding="utf-8") as f:
                user_raw = f.read()
        except FileNotFoundError:
            logger.warning("找不到 user template，使用內建預設")
            user_raw = _DEFAULT_ANALYSIS_PROMPT

        # 從 system prompt 取版本號
        version = "1.0.0"
        if system_raw.startswith("# version:"):
            version = system_raw.splitlines()[0].split(":", 1)[1].strip()
            system_raw = "\n".join(system_raw.splitlines()[1:]).strip()

        # 從 user template 移除版本行與說明區塊，只保留實際 template 內容
        if user_raw.startswith("# version:"):
            lines = user_raw.splitlines()
            # 跳過所有 # 開頭的說明行
            start = next((i for i, l in enumerate(lines) if not l.startswith("#")), 0)
            user_raw = "\n".join(lines[start:]).strip()

        # 合併：system prompt 作為 system_prompt，user template 作為 analysis_template
        combined_system = _SYSTEM_PREAMBLE
        if system_raw:
            combined_system = system_raw + "\n\n" + _SYSTEM_PREAMBLE

        return cls(
            version=version,
            system_prompt=combined_system,
            analysis_template=user_raw,
        )


_SYSTEM_PREAMBLE = """你是一位專精中文小說敘事分析的文學評論 AI。
你的任務是對給定的小說場景進行「局心欲變」框架分析。
你必須：
1. 嚴格以 JSON 格式輸出，不得添加 markdown code fence 或任何額外文字
2. 每個分析維度都必須包含 evidence_quotes，引用原文中的實際語句
3. 引用必須是原文的直接摘錄，不得改寫或虛構
4. 若場景文字不足以支撐某項分析，在該欄位說明原因，但不得省略欄位
5. confidence_score 必須誠實反映分析的確定程度"""

_DEFAULT_ANALYSIS_PROMPT = """# version: 1.0.0
請分析以下小說場景，輸出符合「局心欲變」框架的 JSON 分析卡。

## 場景文字
{scene_text}

## 場景基本資訊
- 核心角色：{focal_character}
- 章節：{chapter_number}，場景序號：{scene_number}

## 輸出格式要求
請嚴格輸出以下 JSON 結構，所有欄位都必須填寫：

{{
  "focal_character": "<核心角色名>",
  "secondary_characters": ["<角色1>", "<角色2>"],
  "situation": {{
    "external_situation": "<外部局勢描述>",
    "power_dynamics": "<權力關係分析>",
    "risks_and_constraints": "<風險與限制>",
    "active_party": "<主動方>",
    "passive_party": "<被動方>",
    "resource_holders": "<資源持有者>",
    "evidence_quotes": [
      {{"text": "<原文引用>", "chapter_hint": "<位置提示>", "relevance": "<此引用如何支持分析>"}}
    ]
  }},
  "desire": {{
    "explicit_desire": "<顯性欲望>",
    "implicit_desire": "<隱性欲望>",
    "true_objective": "<真正目標>",
    "desire_conflicts": "<欲望衝突>",
    "obstacles": "<阻礙>",
    "evidence_quotes": [
      {{"text": "<原文引用>", "chapter_hint": "<位置提示>", "relevance": "<此引用如何支持分析>"}}
    ]
  }},
  "mind_shift": {{
    "before_mindset": "<場景前心態>",
    "trigger_event": "<觸發事件>",
    "after_mindset": "<場景後心態>",
    "shift_type": "<emotion|values|strategy|identity|stance|none>",
    "shift_description": "<轉變描述>",
    "is_reversible": true,
    "evidence_quotes": [
      {{"text": "<原文引用>", "chapter_hint": "<位置提示>", "relevance": "<此引用如何支持分析>"}}
    ]
  }},
  "judgment": {{
    "match_level": "<full|partial|weak|none>",
    "matches_framework": true,
    "reasoning": "<判定理由>",
    "confidence_score": 0.85,
    "missing_dimensions": [],
    "key_evidence_quotes": [
      {{"text": "<最關鍵原文引用>", "chapter_hint": "<位置提示>", "relevance": "<此引用如何支持判定>"}}
    ]
  }}
}}"""


# ---------------------------------------------------------------------------
# 主分析器
# ---------------------------------------------------------------------------


@dataclass
class AnalysisContext:
    """傳入分析器的場景上下文"""
    scene_id: str
    book_id: str
    scene_text: str
    chapter_number: int
    scene_number: int
    focal_character: str
    known_characters: list[str] = field(default_factory=list)
    preceding_scene_summary: Optional[str] = None  # 給 LLM 的前情提要


@dataclass
class AnalysisResult:
    """分析成功結果"""
    card: SceneFrameworkCardSchema
    retry_count: int
    total_tokens: int


class FrameworkAnalyzer:
    """
    「局心欲變」框架分析器。

    典型使用方式：
        analyzer = FrameworkAnalyzer(llm_client=OpenAIAdapter(...))
        result = await analyzer.analyze(ctx)
        card = result.card
    """

    MAX_RETRIES = 3
    MIN_CONFIDENCE_THRESHOLD = 0.3  # 低於此值記 warning

    def __init__(
        self,
        llm_client: AbstractLLMClient,
        prompt_config: Optional[PromptConfig] = None,
        prompt_dir: str = "prompts",
        db_path: Optional[str] = None,
    ) -> None:
        self.llm = llm_client
        self.prompt = prompt_config or PromptConfig.load(prompt_dir)
        self.db_path = db_path  # 用於載入 golden examples few-shot
        logger.info(
            "FrameworkAnalyzer 初始化完成，"
            f"model={self.llm.model_id}, "
            f"prompt_version={self.prompt.version}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, ctx: AnalysisContext) -> AnalysisResult:
        """
        對單一場景執行「局心欲變」分析。

        Returns:
            AnalysisResult：包含完整 SceneFrameworkCardSchema

        Raises:
            AnalysisError：三次 retry 後仍失敗
        """
        last_error: Optional[Exception] = None
        total_tokens = 0

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.debug(
                    f"分析場景 {ctx.scene_id}，"
                    f"第 {attempt} 次嘗試，"
                    f"focal_char={ctx.focal_character}"
                )
                messages = self._build_messages(ctx, attempt)
                response = await self.llm.complete(
                    messages,
                    temperature=0.1 + (attempt - 1) * 0.1,  # retry 時略提高 temperature
                    max_tokens=6000,  # 4096 不夠長場景的 JSON 輸出
                )
                total_tokens += response.input_tokens + response.output_tokens

                raw_json = self._extract_json(response.content)
                card = self._parse_and_validate(raw_json, ctx, response)

                if card.judgment.confidence_score < self.MIN_CONFIDENCE_THRESHOLD:
                    logger.warning(
                        f"場景 {ctx.scene_id} 信心分數 "
                        f"{card.judgment.confidence_score:.2f} 低於閾值 "
                        f"{self.MIN_CONFIDENCE_THRESHOLD}"
                    )

                return AnalysisResult(
                    card=card,
                    retry_count=attempt - 1,
                    total_tokens=total_tokens,
                )

            except (LLMResponseParseError, InsufficientEvidenceError) as e:
                last_error = e
                logger.warning(
                    f"場景 {ctx.scene_id} 第 {attempt} 次分析失敗：{e}"
                )

        raise AnalysisError(
            f"場景 {ctx.scene_id} 分析失敗，已重試 {self.MAX_RETRIES} 次。"
            f"最後錯誤：{last_error}"
        ) from last_error

    async def re_analyze_dimension(
        self,
        ctx: AnalysisContext,
        dimension: str,
        existing_card: SceneFrameworkCardSchema,
    ) -> SceneFrameworkCardSchema:
        """
        對已有分析卡的單一維度重新分析（人工審閱後要求修正某維度時使用）。
        dimension: "situation" | "desire" | "mind_shift" | "judgment"
        """
        if dimension not in ("situation", "desire", "mind_shift", "judgment"):
            raise ValueError(f"未知維度：{dimension}")

        prompt = self._build_dimension_reanalysis_prompt(ctx, dimension, existing_card)
        messages = [
            LLMMessage(role="system", content=self.prompt.system_prompt),
            LLMMessage(role="user", content=prompt),
        ]
        response = await self.llm.complete(messages, temperature=0.2)
        raw_json = self._extract_json(response.content)

        updated = existing_card.model_copy(deep=True)
        dim_data = json.loads(raw_json)

        if dimension == "situation":
            updated.situation = SituationAnalysis(**dim_data)
        elif dimension == "desire":
            updated.desire = DesireAnalysis(**dim_data)
        elif dimension == "mind_shift":
            updated.mind_shift = MindShiftAnalysis(**dim_data)
        elif dimension == "judgment":
            updated.judgment = FrameworkJudgment(**dim_data)

        return updated

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self, ctx: AnalysisContext, attempt: int
    ) -> list[LLMMessage]:
        """組裝 LLM messages，第一次嘗試時注入 golden examples few-shot"""
        replacements = {
            "{scene_text}": ctx.scene_text,
            "{focal_character}": ctx.focal_character,
            "{chapter_number}": str(ctx.chapter_number),
            "{scene_number}": str(ctx.scene_number),
            "{scene_id}": ctx.scene_id,
            "{book_title}": "上城之下",
            "{chapter_title}": f"第 {ctx.chapter_number} 章",
            "{scene_position_hint}": "",
            "{known_characters}": "、".join(ctx.known_characters) if ctx.known_characters else "待提取",
            "{preceding_context}": ctx.preceding_scene_summary or "（無）",
        }
        user_content = self.prompt.analysis_template
        for key, val in replacements.items():
            user_content = user_content.replace(key, val)

        # retry 時加強提示
        if attempt > 1:
            user_content = (
                f"[注意：這是第 {attempt} 次嘗試，"
                "請確保輸出有效 JSON 且每個維度都有 evidence_quotes]\n\n"
                + user_content
            )

        # 加入前情提要（若有）
        if ctx.preceding_scene_summary:
            user_content = (
                f"## 前一場景摘要（背景參考）\n{ctx.preceding_scene_summary}\n\n"
                + user_content
            )

        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=self.prompt.system_prompt),
        ]

        # 第一次嘗試時注入 golden examples 作為 few-shot
        if attempt == 1 and self.db_path:
            few_shots = self._load_golden_examples(ctx.book_id)
            for ex in few_shots:
                messages.append(LLMMessage(role="user", content=ex["user_msg"]))
                messages.append(LLMMessage(role="assistant", content=ex["assistant_msg"]))

        messages.append(LLMMessage(role="user", content=user_content))
        return messages

    def _load_golden_examples(
        self, book_id: Optional[str] = None, max_examples: int = 2
    ) -> list[dict]:
        """
        從 SQLite 讀取 is_golden_example=1 的場景，
        重建為 few-shot user/assistant 對。
        優先選同書、再選全域。最多 max_examples 筆。
        """
        import sqlite3

        results: list[dict] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            # 優先同書，再補全域
            candidates: list[sqlite3.Row] = []
            if book_id:
                candidates = conn.execute(
                    """SELECT scene_text, focal_character, situation, desire, mind_shift,
                              match_level, confidence_score, reviewer_notes,
                              chapter_number, scene_number
                       FROM scene_framework_cards
                       WHERE is_golden_example=1 AND book_id=?
                       ORDER BY RANDOM() LIMIT ?""",
                    (book_id, max_examples),
                ).fetchall()

            if len(candidates) < max_examples:
                need = max_examples - len(candidates)
                extra_where = "AND book_id!=?" if (book_id and candidates) else ""
                extra_params = [book_id] if (book_id and candidates) else []
                extra = conn.execute(
                    f"""SELECT scene_text, focal_character, situation, desire, mind_shift,
                               match_level, confidence_score, reviewer_notes,
                               chapter_number, scene_number
                        FROM scene_framework_cards
                        WHERE is_golden_example=1 {extra_where}
                        ORDER BY RANDOM() LIMIT ?""",
                    extra_params + [need],
                ).fetchall()
                candidates = list(candidates) + list(extra)

            conn.close()

            for row in candidates:
                d = dict(row)
                scene_text = (d.get("scene_text") or "").strip()
                if not scene_text:
                    continue

                # 重建 user 問句（簡化版，只帶核心資訊）
                user_msg = (
                    f"請分析以下小說場景，核心角色：{d.get('focal_character', '未知')}\n\n"
                    f"## 場景文字\n{scene_text[:1500]}"  # 限長避免 context 爆炸
                )

                # 重建 assistant 回答（從 DB 存的 JSON 欄位組合）
                try:
                    situation = json.loads(d.get("situation") or "{}")
                    desire    = json.loads(d.get("desire") or "{}")
                    mind_shift = json.loads(d.get("mind_shift") or "{}")
                except json.JSONDecodeError:
                    continue  # 壞資料跳過

                # 附上 reviewer_notes 作為補充說明（若有）
                note = d.get("reviewer_notes") or ""
                annotation = f"\n# 人工標注備注：{note}" if note else ""

                assistant_msg = json.dumps(
                    {
                        "focal_character": d.get("focal_character", ""),
                        "situation": situation,
                        "desire": desire,
                        "mind_shift": mind_shift,
                        "judgment": {
                            "match_level": d.get("match_level", "partial"),
                            "matches_framework": d.get("match_level") in ("full", "partial"),
                            "confidence_score": float(d.get("confidence_score") or 0.7),
                            "reasoning": "（人工審核確認的 golden example）",
                            "key_evidence_quotes": situation.get("evidence_quotes", [])[:1],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + annotation

                results.append({"user_msg": user_msg, "assistant_msg": assistant_msg})

        except Exception as e:
            logger.warning(f"載入 golden examples 失敗，跳過 few-shot：{e}")

        return results

    @staticmethod
    def _extract_json(raw: str) -> str:
        """
        從 LLM 輸出中提取 JSON。
        處理模型常見的輸出問題：
        1. 包在 ```json ... ``` 裡
        2. 前後有多餘文字
        3. 單引號代替雙引號（部分模型的壞習慣）
        """
        # 嘗試找 code fence
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fence_match:
            return fence_match.group(1)

        # 嘗試找最外層的 { ... }
        brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace_match:
            return brace_match.group(0)

        raise LLMResponseParseError(
            f"無法從 LLM 輸出中提取 JSON。原始輸出前 200 字：{raw[:200]}"
        )

    def _parse_and_validate(
        self,
        raw_json: str,
        ctx: AnalysisContext,
        response: LLMResponse,
    ) -> SceneFrameworkCardSchema:
        """解析 JSON 並構建 SceneFrameworkCardSchema"""
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise LLMResponseParseError(f"JSON 解析失敗：{e}\n原始：{raw_json[:300]}") from e

        # 驗證各維度的 evidence_quotes 存在且非空
        for dim in ("situation", "desire", "mind_shift"):
            quotes = data.get(dim, {}).get("evidence_quotes", [])
            if not quotes:
                raise InsufficientEvidenceError(
                    f"維度 '{dim}' 缺少 evidence_quotes，"
                    f"場景 {ctx.scene_id}"
                )

        judgment_quotes = data.get("judgment", {}).get("key_evidence_quotes", [])
        if not judgment_quotes:
            raise InsufficientEvidenceError(
                f"judgment 缺少 key_evidence_quotes，場景 {ctx.scene_id}"
            )

        try:
            card = SceneFrameworkCardSchema(
                scene_id=ctx.scene_id,
                book_id=ctx.book_id,
                chapter_number=ctx.chapter_number,
                scene_number=ctx.scene_number,
                focal_character=data.get("focal_character", ctx.focal_character),
                secondary_characters=data.get("secondary_characters", []),
                is_negotiation_scene=data.get("is_negotiation_scene", False),
                negotiation_pattern_tags=data.get("negotiation_pattern_tags", []),
                scene_labels=data.get("scene_labels", []),
                situation=SituationAnalysis(**data["situation"]),
                desire=DesireAnalysis(**data["desire"]),
                mind_shift=MindShiftAnalysis(**data["mind_shift"]),
                judgment=FrameworkJudgment(**data["judgment"]),
                model_used=response.model,
                prompt_version=self.prompt.version,
                raw_llm_response=response.content,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise LLMResponseParseError(
                f"Schema 驗證失敗：{e}\n資料：{json.dumps(data, ensure_ascii=False)[:400]}"
            ) from e

        return card

    def _build_dimension_reanalysis_prompt(
        self,
        ctx: AnalysisContext,
        dimension: str,
        existing_card: SceneFrameworkCardSchema,
    ) -> str:
        """針對單一維度重分析的 prompt"""
        dim_names = {
            "situation": "局（外部局勢）",
            "desire": "欲（欲望與動機）",
            "mind_shift": "心變（心態轉變）",
            "judgment": "框架判定",
        }
        return (
            f"請重新分析以下場景的「{dim_names[dimension]}」維度。\n\n"
            f"## 場景文字\n{ctx.scene_text}\n\n"
            f"## 核心角色\n{ctx.focal_character}\n\n"
            f"## 其他維度的分析參考\n"
            f"（請在重分析時參考，但只輸出指定維度的 JSON）\n"
            f"局：{existing_card.situation.model_dump_json(ensure_ascii=False)}\n"
            f"欲：{existing_card.desire.model_dump_json(ensure_ascii=False)}\n"
            f"心變：{existing_card.mind_shift.model_dump_json(ensure_ascii=False)}\n\n"
            f"請只輸出 '{dimension}' 維度的 JSON 物件，格式與原始 schema 一致。"
        )


# ---------------------------------------------------------------------------
# Mock Adapter（用於測試與開發，無需真實 LLM）
# ---------------------------------------------------------------------------


class MockLLMClient(AbstractLLMClient):
    """
    開發與測試用 mock。
    回傳固定結構的假分析結果，讓整個 pipeline 可以跑通而不呼叫真實 API。
    """

    @property
    def model_id(self) -> str:
        return "mock-v1"

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:
        mock_card = {
            "focal_character": "主角",
            "secondary_characters": ["配角A"],
            "situation": {
                "external_situation": "[Mock] 場景外部局勢",
                "power_dynamics": "[Mock] 權力關係",
                "risks_and_constraints": "[Mock] 風險限制",
                "active_party": "[Mock] 主動方",
                "passive_party": "[Mock] 被動方",
                "resource_holders": "[Mock] 資源持有者",
                "evidence_quotes": [
                    {
                        "text": "[Mock 原文引用]",
                        "chapter_hint": "第一章",
                        "relevance": "[Mock] 支持局勢分析",
                    }
                ],
            },
            "desire": {
                "explicit_desire": "[Mock] 顯性欲望",
                "implicit_desire": "[Mock] 隱性欲望",
                "true_objective": "[Mock] 真正目標",
                "desire_conflicts": "[Mock] 欲望衝突",
                "obstacles": "[Mock] 阻礙",
                "evidence_quotes": [
                    {
                        "text": "[Mock 原文引用]",
                        "chapter_hint": "第一章",
                        "relevance": "[Mock] 支持欲望分析",
                    }
                ],
            },
            "mind_shift": {
                "before_mindset": "[Mock] 場景前心態",
                "trigger_event": "[Mock] 觸發事件",
                "after_mindset": "[Mock] 場景後心態",
                "shift_type": "strategy",
                "shift_description": "[Mock] 從防禦轉為主動",
                "is_reversible": True,
                "evidence_quotes": [
                    {
                        "text": "[Mock 原文引用]",
                        "chapter_hint": "第一章",
                        "relevance": "[Mock] 支持心變分析",
                    }
                ],
            },
            "judgment": {
                "match_level": "partial",
                "matches_framework": True,
                "reasoning": "[Mock] 判定理由",
                "confidence_score": 0.72,
                "missing_dimensions": [],
                "key_evidence_quotes": [
                    {
                        "text": "[Mock 關鍵原文引用]",
                        "chapter_hint": "第一章",
                        "relevance": "[Mock] 最關鍵支持",
                    }
                ],
            },
        }
        return LLMResponse(
            content=json.dumps(mock_card, ensure_ascii=False),
            model=self.model_id,
            input_tokens=500,
            output_tokens=800,
        )

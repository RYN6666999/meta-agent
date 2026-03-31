"""
fallback_router.py — 治理層：主引擎失敗時自動切換備用引擎

設計原則：
  - Golem（Gemini/OpenRouter）只負責出力，不決定重試邏輯
  - 本層決定：何時重試、等多久、何時切換引擎
  - ContentBlockedError 直接跳過，不切 fallback（內容問題，換引擎也沒用）

典型配置：
  primary   = GeminiClient（免費配額）
  secondary = OpenRouterClient(haiku)（付費備用，穩定）

使用：
  router = FallbackRouter(primary=gemini, secondary=openrouter_haiku)
  analyzer = FrameworkAnalyzer(llm_client=router, ...)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from backend.app.services.framework_analyzer import (
    AbstractLLMClient,
    LLMMessage,
    LLMResponse,
)
from services.llm.gemini_adapter import ContentBlockedError, QuotaExhaustedError

logger = logging.getLogger(__name__)


class FallbackRouter(AbstractLLMClient):
    """
    主引擎（primary）失敗時切換備用引擎（secondary）。

    重試策略（由治理層控制，Golem 不知情）：
      QuotaExhaustedError → 等 wait_seconds → 再試一次 primary
                         → 仍失敗 → 切 secondary（不等待）
      ContentBlockedError → 直接往上拋（換引擎也沒用）
      其他 ValueError     → 切 secondary
    """

    def __init__(
        self,
        primary: AbstractLLMClient,
        secondary: AbstractLLMClient,
        wait_seconds: float = 15.0,   # quota 限速後等多久再試
        max_primary_retries: int = 1, # 切換前對 primary 重試幾次
    ) -> None:
        self.primary   = primary
        self.secondary = secondary
        self._wait     = wait_seconds
        self._max_retries = max_primary_retries
        self._consecutive_quota_fails = 0  # 連續 quota 失敗計數
        self._skip_primary = False          # 連續失敗太多次就暫停 primary

    @property
    def model_id(self) -> str:
        return f"fallback({self.primary.model_id} → {self.secondary.model_id})"

    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:

        # 若 primary 近期連續失敗 3 次，暫時直接走 secondary（省等待時間）
        if self._skip_primary:
            logger.info("[FallbackRouter] primary 暫停，直接走 secondary")
            return await self._call_secondary(messages, temperature=temperature, max_tokens=max_tokens)

        # ── 嘗試 primary ──
        for attempt in range(1, self._max_retries + 2):  # +2 = 至少跑一次
            try:
                result = await self.primary.complete(
                    messages, temperature=temperature, max_tokens=max_tokens)
                # 成功：重置計數
                self._consecutive_quota_fails = 0
                return result

            except ContentBlockedError:
                # 內容問題，切換引擎也沒用，直接往上拋讓 batch 跳過此場景
                raise

            except QuotaExhaustedError as e:
                self._consecutive_quota_fails += 1
                if self._consecutive_quota_fails >= 3:
                    self._skip_primary = True
                    logger.warning(
                        f"[FallbackRouter] primary 連續 {self._consecutive_quota_fails} "
                        f"次 quota 失敗，暫停 primary"
                    )

                if attempt <= self._max_retries:
                    wait = self._wait
                    print(f"  [FallbackRouter] primary quota 耗盡，等 {wait:.0f}s 後重試 "
                          f"（{attempt}/{self._max_retries}）")
                    logger.warning(f"[FallbackRouter] QuotaExhaustedError: {e}，等 {wait}s")
                    await asyncio.sleep(wait)
                    continue

                # 重試耗盡 → 切 secondary
                print(f"  [FallbackRouter] primary 無法使用，切換到 {self.secondary.model_id}")
                logger.warning(f"[FallbackRouter] 切換 secondary: {e}")
                return await self._call_secondary(messages, temperature=temperature, max_tokens=max_tokens)

            except Exception as e:
                # 其他錯誤（400/403/格式異常）→ 直接切 secondary
                logger.warning(f"[FallbackRouter] primary 非 quota 錯誤 ({e})，切 secondary")
                return await self._call_secondary(messages, temperature=temperature, max_tokens=max_tokens)

        # 理論上不會到這裡
        return await self._call_secondary(messages, temperature=temperature, max_tokens=max_tokens)

    async def _call_secondary(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        try:
            return await self.secondary.complete(
                messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            raise RuntimeError(
                f"[FallbackRouter] primary 和 secondary 都失敗：{e}"
            ) from e

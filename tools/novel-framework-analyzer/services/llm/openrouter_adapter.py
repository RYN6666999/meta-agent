"""
services/llm/openrouter_adapter.py
====================================
OpenRouter adapter — 相容 OpenAI chat completions API。
支援 Claude Haiku（便宜快速）、Claude Sonnet（高品質）、Gemini Flash 等。

推薦模型（中文小說分析）：
  - anthropic/claude-haiku-4-5          ← 便宜，速度快，中文好
  - anthropic/claude-sonnet-4-5         ← 品質最高，貴一點
  - google/gemini-flash-1.5             ← 超便宜，中文可接受
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import httpx

from backend.app.services.framework_analyzer import (
    AbstractLLMClient,
    LLMMessage,
    LLMResponse,
)

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterClient(AbstractLLMClient):

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-haiku-4-5",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def model_id(self) -> str:
        return f"openrouter/{self._model}"

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:
        payload: Dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/novel-framework-analyzer",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=self.model_id,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )

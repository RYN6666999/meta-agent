"""
services/llm/ollama_adapter.py
==============================
Ollama 本地 LLM adapter。
支援任何 Ollama 已下載的模型（qwen2.5:7b、llama3.2 等）。

使用：
    client = OllamaClient(model="qwen2.5:7b")
    analyzer = FrameworkAnalyzer(llm_client=client)
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

import httpx

from backend.app.services.framework_analyzer import (
    AbstractLLMClient,
    LLMMessage,
    LLMResponse,
)

logger = logging.getLogger(__name__)


class OllamaClient(AbstractLLMClient):
    """
    呼叫本地 Ollama 服務。
    預設端點：http://localhost:11434
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,  # 本地模型較慢，給寬裕時間
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    @property
    def model_id(self) -> str:
        return f"ollama/{self._model}"

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["message"]["content"]
        usage = data.get("prompt_eval_count", 0), data.get("eval_count", 0)

        logger.debug(f"Ollama {self._model} 完成，輸入={usage[0]} 輸出={usage[1]} tokens")
        return LLMResponse(
            content=content,
            model=self.model_id,
            input_tokens=usage[0],
            output_tokens=usage[1],
            raw=data,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self._base_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]

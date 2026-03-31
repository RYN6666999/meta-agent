"""
gemini_adapter.py — Google Gemini 直連 Adapter（免費額度）

使用原生 Gemini generateContent API，不走 OpenRouter。
免費額度（Gemini 1.5 Flash / 2.0 Flash）：
  - 15 req/min，1M token/min，1,500 req/day

端點：https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

import httpx

from backend.app.services.framework_analyzer import (
    AbstractLLMClient,
    LLMMessage,
    LLMResponse,
)

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

GEMINI_FREE_MODELS = {
    "flash25":    "gemini-2.5-flash",         # 最新最強，免費 ← 推薦
    "flash":      "gemini-flash-latest",      # 穩定別名
    "flash-lite": "gemini-flash-lite-latest", # 最快最省
}


class GeminiClient(AbstractLLMClient):
    """直接呼叫 Google AI Studio generateContent API，走免費配額。"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model   = model
        self._timeout = timeout

    @property
    def model_id(self) -> str:
        return f"google/{self._model}"

    def _to_gemini_contents(self, messages: List[LLMMessage]) -> list:
        """將 OpenAI messages 格式轉成 Gemini contents 格式。
        system prompt 合併到第一個 user message。
        """
        contents = []
        system_text = ""
        for m in messages:
            if m.role == "system":
                system_text = m.content
            elif m.role == "user":
                text = f"{system_text}\n\n{m.content}" if system_text else m.content
                contents.append({"role": "user", "parts": [{"text": text}]})
                system_text = ""  # 只合併一次
            elif m.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": m.content}]})
        return contents

    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 6000,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:
        url = f"{GEMINI_BASE}/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "contents": self._to_gemini_contents(messages),
            "generationConfig": {
                "temperature":   temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        data: dict = {}
        for attempt in range(5):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload,
                                         headers={"Content-Type": "application/json"})

            if resp.status_code == 429:
                wait = 4 + attempt * 4   # 4, 8, 12, 16, 20s
                logger.warning(f"Gemini 429 rate limit，{wait}s 後重試（attempt {attempt+1}/5）")
                print(f"Gemini 429 rate limit，{wait}s 後重試（attempt {attempt+1}/5）")
                await asyncio.sleep(wait)
                continue

            if resp.status_code == 503:
                wait = 5 * (attempt + 1)
                logger.warning(f"Gemini 503 overload，{wait}s 後重試")
                await asyncio.sleep(wait)
                continue

            if resp.status_code == 400:
                try:
                    detail = resp.json().get("error", {}).get("message", resp.text[:200])
                except Exception:
                    detail = resp.text[:200]
                raise ValueError(f"Gemini 400：{detail}")

            if resp.status_code == 403:
                raise ValueError(
                    "Gemini 403：API key 無效或未啟用 Generative Language API。\n"
                    "請至 https://aistudio.google.com/apikey 確認 key 正確，\n"
                    "並確認已在 Google Cloud Console 啟用 Generative Language API。"
                )

            resp.raise_for_status()

            # Gemini 偶爾用 HTTP 200 夾帶 error body（如 quota exceeded）
            data = resp.json()
            if "error" in data:
                err = data["error"]
                code = err.get("code", 0)
                msg  = err.get("message", "unknown error")
                if code == 429 or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in str(err):
                    wait = 4 + attempt * 8   # 4, 12, 20, 28, 36s
                    logger.warning(f"Gemini quota (200 body)，{wait}s 後重試（attempt {attempt+1}/5）")
                    print(f"Gemini quota exceeded，{wait}s 後重試（attempt {attempt+1}/5）")
                    await asyncio.sleep(wait)
                    data = {}   # reset so we know retries were exhausted
                    continue
                raise ValueError(f"Gemini error {code}：{msg[:200]}")
            break
        else:
            # for/else：所有 5 次重試都因 rate limit / quota 耗盡
            raise ValueError("Gemini 已達最大重試次數（5 次），quota 可能已耗盡，請稍後再試。")

        if not data:
            raise ValueError("Gemini 回應為空（data 未被賦值），請檢查網路或 API key。")

        # 解析 Gemini 回應格式
        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Gemini 回應格式異常：{e} | 原始：{str(data)[:300]}")

        usage = data.get("usageMetadata", {})
        return LLMResponse(
            content=content,
            model=self.model_id,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            raw=data,
        )

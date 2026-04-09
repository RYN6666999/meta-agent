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
    "flash25":    "gemini-2.5-flash",
    "flash":      "gemini-flash-latest",
    "flash-lite": "gemini-flash-lite-latest",
}


class QuotaExhaustedError(Exception):
    """Gemini rate limit / quota 耗盡 — 治理層可拿來觸發 fallback"""


class ContentBlockedError(Exception):
    """Gemini 內容被安全過濾器攔截 — 跳過此場景，不需 fallback"""


class GeminiClient(AbstractLLMClient):
    """直接呼叫 Google AI Studio generateContent API。

    設計原則：Golem 只負責出力，不負責重試逐輯。
    429 / quota 耗盡→ QuotaExhaustedError
    內容被擋    → ContentBlockedError
    其他失敗    → ValueError
    """

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
        contents = []
        system_text = ""
        for m in messages:
            if m.role == "system":
                system_text = m.content
            elif m.role == "user":
                text = f"{system_text}\n\n{m.content}" if system_text else m.content
                contents.append({"role": "user", "parts": [{"text": text}]})
                system_text = ""
            elif m.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": m.content}]})
        return contents

    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:
        url = f"{GEMINI_BASE}/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "contents": self._to_gemini_contents(messages),
            "generationConfig": {
                "temperature":     temperature,
                "maxOutputTokens": max_tokens,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            ],
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload,
                                     headers={"Content-Type": "application/json"})

        # ── HTTP 錯誤：將控制權交還沿絲層 ──
        if resp.status_code == 429:
            msg = ""
            try:
                msg = resp.json().get("error", {}).get("message", "")[:120]
            except Exception:
                pass
            raise QuotaExhaustedError(f"Gemini 429: {msg}")

        if resp.status_code == 503:
            raise QuotaExhaustedError("Gemini 503: 服務過載")

        if resp.status_code == 400:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", resp.text[:200])
            except Exception:
                detail = resp.text[:200]
            raise ValueError(f"Gemini 400：{detail}")

        if resp.status_code == 403:
            raise ValueError(
                "Gemini 403：API key 無效或未啟用 Generative Language API"
            )

        resp.raise_for_status()

        data = resp.json()

        # HTTP 200 但 body 內含 error（quota 超限常見此格式）
        if "error" in data:
            err  = data["error"]
            code = err.get("code", 0)
            msg  = err.get("message", "unknown")
            if code == 429 or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in str(err):
                raise QuotaExhaustedError(f"Gemini quota (200 body): {msg[:120]}")
            raise ValueError(f"Gemini error {code}：{msg[:200]}")

        # 內容被安全過濾器攔截
        if "promptFeedback" in data and "blockReason" in data.get("promptFeedback", {}):
            reason = data["promptFeedback"]["blockReason"]
            raise ContentBlockedError(f"Gemini 內容被攔截（{reason}）")

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
            # 停用安全過濾器，確保學術/文學分析題材不被攔截
            "safetySettings": [
                {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            ],
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
        # 檢查 promptFeedback blockReason（即使加了 safetySettings 仍可能被擋）
        if "promptFeedback" in data and "blockReason" in data.get("promptFeedback", {}):
            reason = data["promptFeedback"]["blockReason"]
            raise ValueError(f"Gemini 內容被攔截（{reason}），跳過此場景")
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

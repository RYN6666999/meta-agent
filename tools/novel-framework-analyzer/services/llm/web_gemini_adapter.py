"""
web_gemini_adapter.py — super-engine daemon Python 橋接器

架構：
  - 啟動一個持久 Node.js daemon（browser 常駐）
  - Python 透過 stdin/stdout JSON lines 與 daemon 通訊
  - 串行送 prompt，daemon 內部自動 recover + retry
  - batch job 結束後 shutdown

依賴：
  /Users/ryan/super-engine  (weblm-driver + scripts/daemon.ts)

環境變數（.env）：
  GEMINI_PROFILE_DIR   — Chrome profile 目錄（必填）
  CHROME_EXECUTABLE    — Chrome binary 路徑（選填）
  GEMINI_HEADED        — "1" 顯示瀏覽器（除錯用）
  GEMINI_TIMEOUT_MS    — 每個 prompt 最大等待 ms（預設 120000）
  GEMINI_MAX_RETRIES   — recover 後最多重試（預設 4）
  GEMINI_INTER_MS      — prompt 間延遲 ms（預設 2000）
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from backend.app.services.framework_analyzer import (
    AbstractLLMClient,
    LLMMessage,
    LLMResponse,
)

logger = logging.getLogger(__name__)

_SUPER_ENGINE_DIR = Path("/Users/ryan/super-engine")
_DAEMON_SCRIPT    = _SUPER_ENGINE_DIR / "scripts" / "daemon.ts"
_TSX_BIN          = _SUPER_ENGINE_DIR / "node_modules" / ".bin" / "tsx"
_NODE_BIN         = Path("/Users/ryan/.nvm/versions/node/v20.18.3/bin/node")


class WebGeminiUnavailableError(RuntimeError):
    """設定不完整或 super-engine 不存在"""


class WebGeminiFatalError(RuntimeError):
    """Daemon 回報 fatal=true，browser 已死，需重啟"""


# ── Daemon 管理（module-level singleton） ────────────────────────────────────
_daemon_proc: Optional[asyncio.subprocess.Process] = None
_daemon_lock = asyncio.Lock()


async def _get_daemon() -> asyncio.subprocess.Process:
    """取得（或啟動）持久 daemon process。"""
    global _daemon_proc

    async with _daemon_lock:
        # 若 daemon 已在跑且沒死，直接回傳
        if _daemon_proc is not None and _daemon_proc.returncode is None:
            return _daemon_proc

        profile_dir = (
            os.environ.get("GEMINI_PROFILE_DIR")
            or os.environ.get("SMOKE_PROFILE_DIR")
        )
        if not profile_dir:
            raise WebGeminiUnavailableError(
                "需要 GEMINI_PROFILE_DIR 環境變數。\n"
                "請在 .env 設定：\n"
                "  GEMINI_PROFILE_DIR=/Users/ryan/Library/Application Support/Google/Chrome/Default"
            )
        if not _DAEMON_SCRIPT.exists():
            raise WebGeminiUnavailableError(
                f"找不到 daemon 腳本：{_DAEMON_SCRIPT}"
            )
        if not _TSX_BIN.exists():
            raise WebGeminiUnavailableError(
                f"找不到 tsx：{_TSX_BIN}\n"
                "請執行：cd /Users/ryan/super-engine && npm install --save-dev tsx"
            )
        if not _NODE_BIN.exists():
            raise WebGeminiUnavailableError(
                f"找不到 node：{_NODE_BIN}"
            )

        env = {
            **os.environ,
            "SMOKE_PROFILE_DIR": profile_dir,
            "GEMINI_TIMEOUT_MS":  os.environ.get("GEMINI_TIMEOUT_MS", "120000"),
            "GEMINI_MAX_RETRIES": os.environ.get("GEMINI_MAX_RETRIES", "4"),
            "GEMINI_INTER_MS":    os.environ.get("GEMINI_INTER_MS", "2000"),
            "GEMINI_HEADED":      os.environ.get("GEMINI_HEADED", "0"),
        }
        chrome = os.environ.get("CHROME_EXECUTABLE")
        if chrome:
            env["CHROME_EXECUTABLE"] = chrome

        logger.info("[WebGemini] 啟動 daemon...")
        print("[WebGemini] 啟動 browser daemon（首次需 10-30 秒）...")

        proc = await asyncio.create_subprocess_exec(
            str(_NODE_BIN), str(_TSX_BIN), str(_DAEMON_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_SUPER_ENGINE_DIR),
            env=env,
        )

        # 讀 stderr 到背景 task
        asyncio.create_task(_pipe_stderr(proc))

        # 等待 ready 信號（__ready__ 或 __init_failed__）
        ready_timeout = 60
        try:
            ready_line = await asyncio.wait_for(
                _read_line(proc), timeout=ready_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise WebGeminiUnavailableError(
                f"Daemon 啟動超時（{ready_timeout}s），請確認 Chrome profile 已登入"
            )

        ready = json.loads(ready_line)
        if not ready.get("ok"):
            proc.kill()
            raise WebGeminiUnavailableError(
                f"Daemon 啟動失敗：{ready.get('error', '未知')}"
            )

        logger.info("[WebGemini] daemon ready")
        print("[WebGemini] ✅ Browser ready，開始分析")
        _daemon_proc = proc
        return proc


async def _read_line(proc: asyncio.subprocess.Process) -> str:
    """從 daemon stdout 讀取一行（阻塞到有資料）"""
    assert proc.stdout is not None
    line = await proc.stdout.readline()
    return line.decode("utf-8", errors="replace").strip()


async def _pipe_stderr(proc: asyncio.subprocess.Process) -> None:
    """把 daemon stderr 轉印到 Python stderr（用於除錯）"""
    assert proc.stderr is not None
    async for line in proc.stderr:
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            logger.debug(f"[daemon] {text}")


async def shutdown_daemon() -> None:
    """強制關閉 daemon（batch 結束時呼叫）。"""
    global _daemon_proc
    if _daemon_proc is not None and _daemon_proc.returncode is None:
        logger.info("[WebGemini] shutting down daemon")
        try:
            assert _daemon_proc.stdin is not None
            _daemon_proc.stdin.close()
            await asyncio.wait_for(_daemon_proc.wait(), timeout=10)
        except Exception:
            _daemon_proc.kill()
        _daemon_proc = None


# ── LLM Client ───────────────────────────────────────────────────────────────
class WebGeminiClient(AbstractLLMClient):
    """
    super-engine daemon 的 AbstractLLMClient 實作。

    - 第一次 complete() 啟動 daemon（browser）
    - 後續呼叫重用同一 daemon（browser 常駐）
    - 每個 prompt 都有唯一 request ID，daemon 保證串行處理
    """

    @property
    def model_id(self) -> str:
        return "web-gemini-daemon"

    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        response_format: Optional[Dict] = None,
    ) -> LLMResponse:
        prompt = self._build_prompt(messages)
        req_id = str(uuid.uuid4())[:8]

        proc = await _get_daemon()

        # 送請求
        req_line = json.dumps({"id": req_id, "prompt": prompt}) + "\n"
        assert proc.stdin is not None
        proc.stdin.write(req_line.encode())
        await proc.stdin.drain()

        # 等回應（daemon 保證每個 req 對應一個 resp）
        timeout_s = int(os.environ.get("GEMINI_TIMEOUT_MS", "120000")) / 1000 + 60
        try:
            resp_line = await asyncio.wait_for(_read_line(proc), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise RuntimeError(f"[WebGemini] req {req_id} 等待回應超時")

        resp = json.loads(resp_line)

        if not resp.get("ok"):
            error = resp.get("error", "未知錯誤")
            if resp.get("fatal"):
                # browser 死透，清掉讓下次重啟
                global _daemon_proc
                _daemon_proc = None
                raise WebGeminiFatalError(f"[WebGemini] browser fatal：{error}")
            raise RuntimeError(f"[WebGemini] prompt 失敗：{error}")

        return LLMResponse(content=resp["text"], model=self.model_id)

    def _build_prompt(self, messages: List[LLMMessage]) -> str:
        parts = []
        for m in messages:
            role    = getattr(m, "role", "user")
            content = getattr(m, "content", "")
            if role == "system":
                parts.append(f"[系統指令]\n{content}")
            elif role == "assistant":
                parts.append(f"[AI]\n{content}")
            else:
                parts.append(content)
        return "\n\n".join(parts)


def make_web_gemini_client() -> Optional[WebGeminiClient]:
    """安全工廠：設定不完整時回傳 None。"""
    profile = (
        os.environ.get("GEMINI_PROFILE_DIR")
        or os.environ.get("SMOKE_PROFILE_DIR")
    )
    if not profile:
        logger.warning("[WebGemini] GEMINI_PROFILE_DIR 未設定，跳過")
        return None
    if not _DAEMON_SCRIPT.exists():
        logger.warning(f"[WebGemini] daemon 腳本不存在：{_DAEMON_SCRIPT}")
        return None
    if not _TSX_BIN.exists():
        logger.warning(f"[WebGemini] tsx 不存在：{_TSX_BIN}，請執行 cd /Users/ryan/super-engine && npm install --save-dev tsx")
        return None
    return WebGeminiClient()

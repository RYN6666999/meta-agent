from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.requests import Request
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.agent_loop import parse_golem_protocol, run_protocol_loop
from common.config import BASE_DIR, ENV_FILE, PERSONA_REPORTS_DIR, STATUS_FILE, USERS_DIR
from common.identity import normalize_id
from common.status_store import load_status as shared_load_status
from common.status_store import save_status as shared_save_status

REGISTRY_FILE = BASE_DIR / "memory" / "persona-registry.json"
BACKEND_FILE = BASE_DIR / "memory-mcp" / "server.py"
TRACE_DIRS = [
    BASE_DIR / "truth-source",
    BASE_DIR / "error-log",
    BASE_DIR / "memory",
]


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
    return data


ENV = load_env()
API_KEY = ENV.get("META_AGENT_API_KEY") or ENV.get("API_KEY") or ENV.get("N8N_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or ENV.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET") or ENV.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_MAX_REPLY_CHARS = 3500
SYNC_SCRIPT_OBSIDIAN = BASE_DIR / "scripts" / "obsidian-ingest.py"
SYNC_SCRIPT_HEALTH = BASE_DIR / "scripts" / "health_check.py"


def load_backend() -> Any:
    spec = importlib.util.spec_from_file_location("meta_agent_memory_backend", BACKEND_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load backend from {BACKEND_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backend = load_backend()

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="meta-agent external brain API",
    version="0.2.0",
    description="HTTP wrapper around the existing memory-mcp backend.",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class QueryRequest(BaseModel):
    q: str = Field(..., min_length=2)
    mode: str = Field(default="hybrid")
    user_id: str = Field(default="", max_length=64)


class IngestRequest(BaseModel):
    content: str = Field(..., min_length=50, max_length=4000)
    mem_type: str = Field(default="verified_truth")
    title: str = Field(default="")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    submitted_by: str = Field(default="external-client", min_length=2, max_length=120)
    source_session: str = Field(default="", max_length=120)
    user_id: str = Field(default="", max_length=64)


class PersonaSwitchRequest(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)


class LogErrorRequest(BaseModel):
    root_cause: str = Field(..., min_length=5)
    solution: str = Field(..., min_length=5)
    topic: str = Field(default="")
    context: str = Field(default="")


class ProtocolParseRequest(BaseModel):
    raw_response: str = Field(..., min_length=1)


class ProtocolLoopRequest(BaseModel):
    user_input: str = Field(..., min_length=1)
    raw_response: str = Field(..., min_length=1)
    persist_memory: bool = Field(default=True)
    execute_actions: bool = Field(default=True)


class TelegramChat(BaseModel):
    id: int
    type: str = "private"


class TelegramUser(BaseModel):
    id: int
    username: str | None = None


class TelegramMessage(BaseModel):
    message_id: int
    text: str | None = None
    chat: TelegramChat
    from_user: TelegramUser | None = Field(default=None, alias="from")


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not API_KEY:
        raise HTTPException(status_code=503, detail="API key is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


def load_status() -> dict[str, Any]:
    return shared_load_status()


def save_status(data: dict[str, Any]) -> None:
    shared_save_status(data)


def update_usage(path: str, method: str, status_code: int) -> None:
    status = load_status()
    usage = status.get("api_usage", {})
    per_endpoint = usage.get("per_endpoint", {})
    key = f"{method} {path}"

    endpoint_entry = per_endpoint.get(key, {"count": 0, "last_status_code": 0, "last_called_at": ""})
    endpoint_entry["count"] = int(endpoint_entry.get("count", 0)) + 1
    endpoint_entry["last_status_code"] = status_code
    endpoint_entry["last_called_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    per_endpoint[key] = endpoint_entry

    usage["total_calls"] = int(usage.get("total_calls", 0)) + 1
    usage["per_endpoint"] = per_endpoint
    usage["last_call"] = {
        "path": path,
        "method": method,
        "status_code": status_code,
        "called_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    status["api_usage"] = usage
    save_status(status)


def _sanitize_persona_id(raw: str) -> str:
    return normalize_id(raw=raw, default="default", max_len=64)


def load_registry() -> dict[str, Any]:
    if not REGISTRY_FILE.exists():
        return {"active_persona": "default", "personas": {}}
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"active_persona": "default", "personas": {}}
        if "personas" not in data or not isinstance(data.get("personas"), dict):
            data["personas"] = {}
        if "active_persona" not in data:
            data["active_persona"] = "default"
        return data
    except Exception:
        return {"active_persona": "default", "personas": {}}


def save_registry(data: dict[str, Any]) -> None:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_persona_config(persona_id: str) -> dict[str, Any]:
    return {
        "name": persona_id,
        "backend": "lightrag",
        "memory_namespace": persona_id,
        "workflow": {
            "tech_radar": {
                "enabled": False,
                "queries": [],
                "max_results_per_query": 3,
                "report_style": "generic",
            }
        },
    }


def ensure_persona_in_registry(persona_id: str) -> None:
    safe = _sanitize_persona_id(persona_id)
    reg = load_registry()
    personas = reg.get("personas", {})
    if safe not in personas:
        personas[safe] = _default_persona_config(safe)
        reg["personas"] = personas
        save_registry(reg)


def configured_personas() -> set[str]:
    reg = load_registry()
    personas = reg.get("personas", {})
    return {_sanitize_persona_id(k) for k in personas.keys()}


def get_active_persona() -> str:
    reg = load_registry()
    return _sanitize_persona_id(str(reg.get("active_persona", "default")))


def set_active_persona(persona_id: str) -> str:
    safe = _sanitize_persona_id(persona_id)
    ensure_persona_in_registry(safe)

    reg = load_registry()
    reg["active_persona"] = safe
    save_registry(reg)

    # 保留 status 同步欄位，避免既有儀表板讀不到
    status = load_status()
    persona = status.get("persona", {})
    persona["active"] = safe
    persona["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status["persona"] = persona
    save_status(status)
    return safe


def resolve_persona_id(request_user_id: str) -> str:
    candidate = (request_user_id or "").strip()
    if not candidate:
        return get_active_persona()
    return _sanitize_persona_id(candidate)


def telegram_ready() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET)


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def send_telegram_text(chat_id: int, text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        return False

    payload = {
        "chat_id": chat_id,
        "text": text[:TELEGRAM_MAX_REPLY_CHARS],
        "disable_web_page_preview": True,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _telegram_api_url("sendMessage"),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            ok = 200 <= getattr(resp, "status", 200) < 300
            if not ok:
                print(f"[telegram] sendMessage non-2xx chat_id={chat_id} status={getattr(resp, 'status', 'unknown')}", flush=True)
            return ok
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        print(f"[telegram] sendMessage http_error chat_id={chat_id} status={exc.code} body={body}", flush=True)
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[telegram] sendMessage error chat_id={chat_id} detail={exc}", flush=True)
        return False


def run_local_script(script_path: Path, timeout_sec: int = 180) -> tuple[bool, str]:
    if not script_path.exists():
        return False, f"missing script: {script_path.name}"
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        output = (completed.stdout or completed.stderr or "").strip().replace("\r", "")
        preview = "\n".join(output.splitlines()[:6])
        ok = completed.returncode == 0
        return ok, preview if preview else f"exit={completed.returncode}"
    except Exception as exc:
        return False, str(exc)


def run_sync_job(mode: str) -> str:
    mode_clean = mode.strip().lower()
    if mode_clean in {"", "quick"}:
        ok, detail = run_local_script(SYNC_SCRIPT_OBSIDIAN, timeout_sec=240)
        state = "ok" if ok else "failed"
        return f"[sync:{state}] obsidian-ingest\n{detail}"

    if mode_clean in {"full", "all"}:
        obs_ok, obs_detail = run_local_script(SYNC_SCRIPT_OBSIDIAN, timeout_sec=240)
        hc_ok, hc_detail = run_local_script(SYNC_SCRIPT_HEALTH, timeout_sec=180)
        overall = "ok" if (obs_ok and hc_ok) else "failed"
        return (
            f"[sync:{overall}] mode=full\n"
            f"obsidian-ingest={'ok' if obs_ok else 'failed'}\n{obs_detail}\n\n"
            f"health-check={'ok' if hc_ok else 'failed'}\n{hc_detail}"
        )

    return "格式錯誤：/sync 或 /sync full"


def render_mobile_status() -> str:
    status = load_status()
    health = status.get("health_check", {}) if isinstance(status, dict) else {}
    e2e = status.get("e2e_memory_extract", {}) if isinstance(status, dict) else {}
    auto_recovery = status.get("auto_recovery", {}) if isinstance(status, dict) else {}

    health_ok = bool(health.get("ok"))
    e2e_ok = bool(e2e.get("ok"))
    h_time = str(health.get("checked_at") or "n/a")
    e_time = str(e2e.get("checked_at") or "n/a")

    last_trigger = auto_recovery.get("last_trigger", {}) if isinstance(auto_recovery, dict) else {}
    last_recovery = str(last_trigger.get("triggered_at") or "n/a")

    return (
        "[mobile status]\n"
        f"health={'ok' if health_ok else 'fail'} @ {h_time}\n"
        f"e2e={'ok' if e2e_ok else 'fail'} @ {e_time}\n"
        f"last_auto_recovery={last_recovery}"
    )


async def handle_telegram_text(text: str, chat_id: int) -> str:
    clean = (text or "").strip()
    if not clean:
        return "請輸入文字訊息，我才能幫你查詢。"

    persona_id = _sanitize_persona_id(f"tg_{chat_id}")
    ensure_persona_in_registry(persona_id)

    if clean.startswith("/start") or clean.startswith("/help"):
        return (
            "可用指令:\n"
            "/q <問題> 查記憶\n"
            "/ingest <內容> 寫入記憶\n"
            "/protocol <GOLEM 回應區塊> 執行 golem/nanoclaw 風格動作\n"
            "/sync 或 /sync full 觸發電腦同步作業\n"
            "/status 查看系統健康度"
        )

    if clean.startswith("/q "):
        query = clean[3:].strip()
        if not query:
            return "格式錯誤：/q 後面要帶查詢內容。"
        if hasattr(backend, "query_memory_structured"):
            data = await backend.query_memory_structured(query, "hybrid", persona_id)
            result = str(data.get("result", "")).strip()
        else:
            result = str(await backend.query_memory(query, "hybrid", persona_id)).strip()
        return result or "查無相關記憶。"

    if clean.startswith("/ingest "):
        content = clean[8:].strip()
        if len(content) < 50:
            return "寫入內容太短，請至少 50 字。"
        result = await backend.ingest_memory(
            f"[CONFIRMED] {content}",
            "verified_truth",
            "telegram-ingest",
            persona_id,
        )
        return result

    if clean.startswith("/protocol "):
        raw = clean[len("/protocol ") :].strip()
        if not raw:
            return "格式錯誤：/protocol 後面要帶 GOLEM 協議內容。"
        loop_result = await run_protocol_loop(
            user_input="telegram-protocol",
            raw_response=raw,
            backend=backend,
            persist_memory=True,
            execute_actions=True,
        )
        parsed = loop_result.get("parsed", {})
        reply = str(parsed.get("reply") or "已執行 protocol。")
        obs_count = len(loop_result.get("observation", []))
        return f"{reply}\n\n[protocol] observations={obs_count}"

    if clean == "/sync":
        return run_sync_job("quick")

    if clean.startswith("/sync "):
        return run_sync_job(clean[len("/sync ") :])

    if clean == "/status":
        return render_mobile_status()

    if hasattr(backend, "query_memory_structured"):
        data = await backend.query_memory_structured(clean, "hybrid", persona_id)
        result = str(data.get("result", "")).strip()
    else:
        result = str(await backend.query_memory(clean, "hybrid", persona_id)).strip()
    return result or "查無相關記憶。你可以用 /ingest 寫入背景後再查詢。"


def list_available_personas() -> list[str]:
    personas = {"default", get_active_persona()}
    personas.update(configured_personas())
    if USERS_DIR.exists():
        for child in USERS_DIR.iterdir():
            if child.is_dir():
                personas.add(_sanitize_persona_id(child.name))
    return sorted(personas)


def find_trace_matches(topic: str, limit: int = 8) -> list[dict[str, Any]]:
    topic_lower = topic.lower()
    matches: list[dict[str, Any]] = []
    for scan_dir in TRACE_DIRS:
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.rglob("*.md")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for idx, line in enumerate(lines, start=1):
                if topic_lower in line.lower():
                    matches.append(
                        {
                            "file": str(path.relative_to(BASE_DIR)),
                            "line": idx,
                            "snippet": line.strip(),
                        }
                    )
                    break
            if len(matches) >= limit:
                return matches
    return matches


def find_trace_matches_for_persona(topic: str, persona_id: str, limit: int = 8) -> list[dict[str, Any]]:
    safe = _sanitize_persona_id(persona_id)
    if safe == "default":
        return find_trace_matches(topic=topic, limit=limit)

    topic_lower = topic.lower()
    matches: list[dict[str, Any]] = []
    scan_dirs = [USERS_DIR / safe, PERSONA_REPORTS_DIR / safe]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.rglob("*.md")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for idx, line in enumerate(lines, start=1):
                if topic_lower in line.lower():
                    matches.append(
                        {
                            "file": str(path.relative_to(BASE_DIR)),
                            "line": idx,
                            "snippet": line.strip(),
                        }
                    )
                    break
            if len(matches) >= limit:
                return matches
    return matches


@app.middleware("http")
async def usage_counter_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/"):
        update_usage(path=request.url.path, method=request.method, status_code=response.status_code)
    return response


@app.get("/api/v1/health")
@limiter.limit("60/minute")
async def health(request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    status = load_status()
    health_status = status.get("health_check", {})
    e2e_status = status.get("e2e_memory_extract", {})
    overall_ok = bool(health_status.get("ok")) and bool(e2e_status.get("ok"))
    return {
        "ok": overall_ok,
        "api": {"ok": True, "version": app.version},
        "health_check": health_status,
        "e2e_memory_extract": e2e_status,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/v1/query")
@limiter.limit("120/minute")
async def query_memory(payload: QueryRequest, request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    persona_id = resolve_persona_id(payload.user_id)
    if hasattr(backend, "query_memory_structured"):
        data = await backend.query_memory_structured(payload.q, payload.mode, persona_id)
        result = data.get("result", "")
        rerank_candidates = data.get("rerank_candidates", [])
        memory_boost_updated = int(data.get("memory_boost_updated", 0))
    else:
        # 向下相容：舊 backend 仍回傳文字
        result = await backend.query_memory(payload.q, payload.mode, persona_id)
        rerank_candidates = []
        memory_boost_updated = 0
    return {
        "ok": True,
        "query": payload.q,
        "mode": payload.mode,
        "user_id": persona_id,
        "persona_id": persona_id,
        "result": result,
        "rerank_candidates": rerank_candidates,
        "memory_boost_updated": memory_boost_updated,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/v1/ingest")
@limiter.limit("30/minute")
async def ingest_memory(payload: IngestRequest, request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    persona_id = resolve_persona_id(payload.user_id)
    metadata_block = (
        "[META]\n"
        f"confidence: {payload.confidence:.2f}\n"
        f"submitted_by: {payload.submitted_by}\n"
        f"source_session: {payload.source_session or 'n/a'}\n"
        "[/META]\n"
    )

    raw_content = payload.content.strip()
    approval_prefix = ""
    if raw_content.startswith("[APPROVED]"):
        approval_prefix = "[APPROVED] "
        raw_content = raw_content[len("[APPROVED]"):].strip()
    elif raw_content.startswith("[CONFIRMED]"):
        approval_prefix = "[CONFIRMED] "
        raw_content = raw_content[len("[CONFIRMED]"):].strip()

    # 重要：審批標記必須維持在最前，才能通過 memory-mcp 風險閘判定。
    enriched_content = f"{approval_prefix}{metadata_block}{raw_content}"
    result = await backend.ingest_memory(enriched_content, payload.mem_type, payload.title, persona_id)
    return {
        "ok": result.startswith("✅"),
        "message": result,
        "metadata": {
            "confidence": payload.confidence,
            "submitted_by": payload.submitted_by,
            "source_session": payload.source_session,
            "user_id": persona_id,
            "persona_id": persona_id,
        },
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/persona/current")
@limiter.limit("120/minute")
async def persona_current(request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    active = get_active_persona()
    return {
        "ok": True,
        "active_persona": active,
        "available_personas": list_available_personas(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/v1/persona/switch")
@limiter.limit("30/minute")
async def persona_switch(payload: PersonaSwitchRequest, request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    active = set_active_persona(payload.persona_id)
    return {
        "ok": True,
        "active_persona": active,
        "available_personas": list_available_personas(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/rules")
@limiter.limit("60/minute")
async def rules(request: Request, category: str = Query(default="all"), _: None = Depends(require_auth)) -> dict[str, Any]:
    result = backend.get_rules(category)
    parsed: Any
    try:
        parsed = json.loads(result)
    except Exception:
        parsed = result
    return {
        "ok": True,
        "category": category,
        "rules": parsed,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/v1/log-error")
@limiter.limit("30/minute")
async def log_error(payload: LogErrorRequest, request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    result = await backend.log_error(
        root_cause=payload.root_cause,
        solution=payload.solution,
        topic=payload.topic,
        context=payload.context,
    )
    return {
        "ok": result.startswith("✅"),
        "message": result,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/trace")
@limiter.limit("60/minute")
async def trace(
    request: Request,
    topic: str = Query(..., min_length=2),
    limit: int = Query(default=8, ge=1, le=20),
    persona_id: str = Query(default="", max_length=64),
    _: None = Depends(require_auth),
) -> dict[str, Any]:
    effective_persona = resolve_persona_id(persona_id)
    matches = find_trace_matches_for_persona(topic=topic, persona_id=effective_persona, limit=limit)
    return {
        "ok": True,
        "topic": topic,
        "persona_id": effective_persona,
        "count": len(matches),
        "matches": matches,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/status")
@limiter.limit("60/minute")
async def status_dashboard(request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    status = load_status()
    return {
        "ok": True,
        "api": {"ok": True, "version": app.version},
        "persona": {
            "active": get_active_persona(),
            "available": list_available_personas(),
        },
        "api_health": status.get("api_health", {}),
        "api_usage": status.get("api_usage", {}),
        "health_check": status.get("health_check", {}),
        "e2e_memory_extract": status.get("e2e_memory_extract", {}),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/telegram/config")
@limiter.limit("60/minute")
async def telegram_config(request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": telegram_ready(),
        "has_bot_token": bool(TELEGRAM_BOT_TOKEN),
        "has_webhook_secret": bool(TELEGRAM_WEBHOOK_SECRET),
        "webhook_path": "/api/v1/telegram/webhook/{secret}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/v1/telegram/webhook/{secret}")
@limiter.limit("120/minute")
async def telegram_webhook(
    secret: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if not telegram_ready():
        raise HTTPException(status_code=503, detail="telegram is not configured")

    if secret != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid webhook secret")

    # Telegram 支援額外 Header secret，雙重驗證可降低被掃描濫打風險。
    if x_telegram_bot_api_secret_token and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid telegram header secret")

    if not payload:
        return {"ok": True, "ignored": True, "reason": "empty-payload"}

    try:
        update = TelegramUpdate.model_validate(payload)
    except Exception:
        return {"ok": True, "ignored": True, "reason": "invalid-payload"}

    message = update.message or update.edited_message
    if message is None:
        return {"ok": True, "ignored": True, "reason": "no-message"}

    incoming_text = (message.text or "").strip()
    print(
        f"[telegram] incoming update_id={update.update_id} chat_id={message.chat.id} text={incoming_text[:120]!r}",
        flush=True,
    )
    if not incoming_text:
        send_telegram_text(message.chat.id, "目前只支援文字訊息。")
        return {"ok": True, "ignored": True, "reason": "no-text"}

    reply = await handle_telegram_text(incoming_text, message.chat.id)
    sent = send_telegram_text(message.chat.id, reply)
    return {
        "ok": True,
        "delivered": sent,
        "chat_id": message.chat.id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/telegram/webhook/{secret}")
@app.head("/api/v1/telegram/webhook/{secret}")
@limiter.limit("120/minute")
async def telegram_webhook_probe(secret: str, request: Request) -> dict[str, Any]:
    if secret != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid webhook secret")
    return {"ok": True, "ignored": True, "reason": "probe"}


@app.post("/api/v1/protocol/parse")
@limiter.limit("60/minute")
async def protocol_parse(payload: ProtocolParseRequest, request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    parsed = parse_golem_protocol(payload.raw_response)
    return {
        "ok": True,
        "parsed": parsed,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/v1/loop")
@limiter.limit("30/minute")
async def protocol_loop(payload: ProtocolLoopRequest, request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
    return await run_protocol_loop(
        user_input=payload.user_input,
        raw_response=payload.raw_response,
        backend=backend,
        persist_memory=payload.persist_memory,
        execute_actions=payload.execute_actions,
    )

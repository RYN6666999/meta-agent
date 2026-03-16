from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.requests import Request
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.agent_loop import parse_golem_protocol, run_protocol_loop

BASE_DIR = Path("/Users/ryan/meta-agent")
ENV_FILE = BASE_DIR / ".env"
STATUS_FILE = BASE_DIR / "memory" / "system-status.json"
BACKEND_FILE = BASE_DIR / "memory-mcp" / "server.py"
USERS_DIR = BASE_DIR / "memory" / "users"
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


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not API_KEY:
        raise HTTPException(status_code=503, detail="API key is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


def load_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_status(data: dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    safe = "".join(ch for ch in (raw or "") if ch.isalnum() or ch in "_-").strip("_-")
    return safe[:64] if safe else "default"


def get_active_persona() -> str:
    status = load_status()
    persona = status.get("persona", {})
    return _sanitize_persona_id(str(persona.get("active", "default")))


def set_active_persona(persona_id: str) -> str:
    status = load_status()
    safe = _sanitize_persona_id(persona_id)
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


def list_available_personas() -> list[str]:
    personas = {"default", get_active_persona()}
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
    _: None = Depends(require_auth),
) -> dict[str, Any]:
    matches = find_trace_matches(topic, limit=limit)
    return {
        "ok": True,
        "topic": topic,
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

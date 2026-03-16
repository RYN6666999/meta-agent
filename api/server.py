from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

BASE_DIR = Path("/Users/ryan/meta-agent")
ENV_FILE = BASE_DIR / ".env"
STATUS_FILE = BASE_DIR / "memory" / "system-status.json"
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


def load_backend() -> Any:
    spec = importlib.util.spec_from_file_location("meta_agent_memory_backend", BACKEND_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load backend from {BACKEND_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backend = load_backend()

app = FastAPI(
    title="meta-agent external brain API",
    version="0.1.0",
    description="HTTP wrapper around the existing memory-mcp backend.",
)


class QueryRequest(BaseModel):
    q: str = Field(..., min_length=2)
    mode: str = Field(default="hybrid")


class IngestRequest(BaseModel):
    content: str = Field(..., min_length=50, max_length=4000)
    mem_type: str = Field(default="verified_truth")
    title: str = Field(default="")


class LogErrorRequest(BaseModel):
    root_cause: str = Field(..., min_length=5)
    solution: str = Field(..., min_length=5)
    topic: str = Field(default="")
    context: str = Field(default="")


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


@app.get("/api/v1/health")
async def health(_: None = Depends(require_auth)) -> dict[str, Any]:
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
async def query_memory(request: QueryRequest, _: None = Depends(require_auth)) -> dict[str, Any]:
    result = await backend.query_memory(request.q, request.mode)
    return {
        "ok": True,
        "query": request.q,
        "mode": request.mode,
        "result": result,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/v1/ingest")
async def ingest_memory(request: IngestRequest, _: None = Depends(require_auth)) -> dict[str, Any]:
    result = await backend.ingest_memory(request.content, request.mem_type, request.title)
    return {
        "ok": result.startswith("✅"),
        "message": result,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/rules")
async def rules(category: str = Query(default="all"), _: None = Depends(require_auth)) -> dict[str, Any]:
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
async def log_error(request: LogErrorRequest, _: None = Depends(require_auth)) -> dict[str, Any]:
    result = await backend.log_error(
        root_cause=request.root_cause,
        solution=request.solution,
        topic=request.topic,
        context=request.context,
    )
    return {
        "ok": result.startswith("✅"),
        "message": result,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/v1/trace")
async def trace(
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

# Code Intelligence Adapter Spec

## Purpose

Provide a narrow internal interface for code-structure intelligence so the repo can consume GitNexus without coupling the rest of the system to any single vendor or transport.

This adapter should support:

- manual developer use
- scripted failure enrichment
- future protocol-loop enrichment

## Design Constraints

- adapter must be optional
- adapter must degrade safely
- adapter output must be compact and machine-readable
- adapter API should not expose GitNexus-specific payloads directly to the rest of the codebase

## Interface

Suggested Python module path:

- `common/code_intelligence.py`

Suggested primary types:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CodeIntelRequest:
    kind: str
    target: str = ""
    query: str = ""
    repo: str = "meta-agent"
    max_depth: int = 3
    include_tests: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeIntelSummary:
    overview: str
    top_symbols: list[str] = field(default_factory=list)
    affected_paths: list[str] = field(default_factory=list)
    processes: list[str] = field(default_factory=list)
    risk_level: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeIntelResult:
    ok: bool
    provider: str
    mode: str
    request_kind: str
    checked_at: str
    available: bool
    summary: CodeIntelSummary | None = None
    error: str = ""
```

Suggested adapter interface:

```python
class CodeIntelligenceAdapter:
    def is_available(self) -> bool:
        raise NotImplementedError

    def overview(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError

    def symbol_context(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError

    def impact(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError

    def process_search(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError
```

## Request Kinds

Use only a small set of stable request kinds:

- `overview`
- `symbol_context`
- `impact`
- `process_search`
- `failure_enrichment`
- `refactor_planning`

`failure_enrichment` can internally call multiple lower-level GitNexus operations and return one merged summary.

## Normalized Output Contract

Every result should be normalized to the same contract regardless of provider.

Required top-level fields:

- `ok`
- `provider`
- `mode`
- `request_kind`
- `checked_at`
- `available`

Required summary fields when `ok=true`:

- `overview`
- `top_symbols`
- `affected_paths`
- `risk_level`

Optional summary fields:

- `processes`
- `raw`

## Adapter Variants

### 1. Null Adapter

Purpose:

- safe fallback when GitNexus is not installed or not indexed

Behavior:

- `is_available()` returns `False`
- all methods return `ok=False`, `available=False`, `provider="none"`

### 2. GitNexus MCP Adapter

Purpose:

- use GitNexus through MCP when running under an agent or toolchain that exposes it

Best use:

- interactive development sessions

### 3. GitNexus Local Command Adapter

Purpose:

- use local `gitnexus` CLI or `gitnexus serve` for scripted enrichment

Best use:

- health/e2e failure enrichment
- local automation

## Integration Points

### `api/agent_loop.py`

Potential use:

- append code-intelligence observations to protocol loop output for development-oriented tasks

Rule:

- only enrich when task intent is code-related

### `api/server.py`

Potential use:

- expose a future internal endpoint for triggering code-intelligence summaries

Rule:

- keep behind auth and do not make it a mandatory dependency for API health

### `scripts/e2e_test.py` and `scripts/health_check.py`

Potential use:

- call `failure_enrichment` after failure classification

Rule:

- auto-recovery first, enrichment second

### `common/status_store.py`

Potential use:

- save normalized adapter results into a dedicated status shard

## Example Machine-Readable Artifact

```json
{
  "ok": true,
  "provider": "gitnexus",
  "mode": "local-cli",
  "request_kind": "failure_enrichment",
  "checked_at": "2026-03-18 12:00:00",
  "available": true,
  "summary": {
    "overview": "Recent changes touch the API surface and status persistence path.",
    "top_symbols": ["run_protocol_loop", "update_status", "save_status"],
    "affected_paths": ["api/agent_loop.py", "common/status_store.py", "api/server.py"],
    "processes": ["protocol_loop", "status_persist"],
    "risk_level": "medium"
  },
  "error": ""
}
```

## Minimal Implementation Sequence

1. Create the types and the null adapter.
2. Add one `get_code_intelligence_adapter()` factory.
3. Add a stub GitNexus adapter with `is_available()` and one `overview()` method.
4. Add one local manual script to test the adapter.
5. Add one status write path for failure enrichment.

## Guardrails

- never store large raw GitNexus responses directly in `memory/system-status.json`
- always summarize before persisting
- cap `affected_paths` and `top_symbols` to a small number for handoff use
- keep provider-specific parsing inside the adapter only
# GitNexus Integration Plan

## Goal

Use GitNexus as a code-intelligence sidecar for this repo without making the existing memory, status, and recovery path depend on it.

The integration target is narrow:

- GitNexus answers code-structure questions.
- meta-agent remains the source of truth for memory, rules, status, recovery, and handoff.

## Non-Goals

- Do not replace LightRAG with GitNexus.
- Do not make `api/server.py` or `memory-mcp/server.py` fail if GitNexus is unavailable.
- Do not move health, e2e, truth-xval, or auto-recovery ownership out of the current repo.

## Current Integration Surface

The existing system already has stable places where code intelligence can attach:

- `api/server.py`: external HTTP surface and future orchestration entrypoint
- `memory-mcp/server.py`: memory backend and shared tool surface
- `api/agent_loop.py`: protocol loop where structured observations can be injected
- `common/status_store.py`: machine-readable status persistence
- `memory/system-status.json`: operator-facing status source
- `scripts/health_check.py` and `scripts/e2e_test.py`: validation and failure hooks

## Decision

Adopt GitNexus as an optional sidecar with a thin local adapter.

Why this shape:

- low risk: no hard dependency in the main path
- high leverage: adds blast radius, symbol context, and process-level code understanding
- good fit: matches the repo's PDCA and machine-readable status discipline

## Phase Plan

### Phase 1: Manual Developer Assist

Objective:

- Index this repo with GitNexus and use it manually during bugfix and refactor work.

Actions:

1. Install and index the repo with GitNexus.
2. Use GitNexus before code changes for symbol context and impact checks.
3. Keep outputs human-consumed only for now.

Verification:

- developer can retrieve symbol context
- developer can retrieve impact for a changed file or symbol
- no existing health or e2e path changes

Rollback:

- stop using GitNexus; no repo logic depends on it

### Phase 2: Assisted Failure Diagnosis

Objective:

- Add GitNexus-generated code impact notes after selected failures.

Trigger points:

- `scripts/e2e_test.py` fail
- `scripts/health_check.py` fail when the root cause points to code-level changes
- repeated errors in the same subsystem within 24 hours

Actions:

1. Add a local adapter that can request `overview`, `context`, and `impact` data.
2. Generate a compact code-impact note for failures.
3. Save the result as a machine-readable artifact under `memory/status/` or a dedicated artifact path.

Verification:

- failure artifacts contain GitNexus context when available
- failure path still completes when GitNexus is unavailable

Rollback:

- disable the adapter call; keep core failure logic unchanged

### Phase 3: Workflow Automation

Objective:

- Automatically enrich handoff, diagnosis, and refactor planning with code intelligence.

Trigger points:

- before generating handoff
- before large refactors
- after git diff detection on high-risk files

Actions:

1. enrich handoff with recent code hotspots and impact summary
2. enrich protocol loop observations with code context for development tasks
3. write code-intelligence summaries into status shards

Verification:

- handoff includes current code risk snapshot
- repeated incidents converge faster because structural context is attached

Rollback:

- fall back to current handoff and error-only artifacts

## Recommended Event Hooks

### Before Code Change

Use GitNexus for:

- symbol context
- blast radius
- process search
- codebase overview

Best targets in this repo:

- `api/server.py`
- `api/agent_loop.py`
- `memory-mcp/server.py`
- `common/status_store.py`
- `common/lightrag_runtime.py`
- `scripts/e2e_test.py`

### After Validation Failure

Use GitNexus for:

- changed symbol impact
- caller and callee inspection
- process grouping around failed paths
- likely adjacent files for regression review

### Before Handoff

Use GitNexus for:

- top impacted modules from the latest changes
- high-centrality files touched recently
- refactor risk summary

## Data Flow

### Failure Enrichment Flow

1. `health_check.py` or `e2e_test.py` detects failure.
2. Existing auto-recovery runs first.
3. If the incident is code-relevant, call the GitNexus adapter.
4. Adapter returns compact code context.
5. Save result into a status shard and optionally reference it from error-log frontmatter.
6. Handoff generator reads the status shard.

### Refactor Planning Flow

1. User or agent marks a refactor target.
2. Adapter queries symbol context and impact.
3. Result is included in planning notes or protocol observations.
4. Existing validation path remains unchanged.

## Status Artifact Proposal

Add one new shard key in `common/status_store.py` when implementation starts:

- `code_intelligence`

Suggested payload shape:

```json
{
  "ok": true,
  "provider": "gitnexus",
  "checked_at": "2026-03-18 12:00:00",
  "repo": "meta-agent",
  "request_kind": "failure_enrichment",
  "target": "scripts/e2e_test.py",
  "summary": {
    "top_symbols": ["run_e2e", "update_status", "replay_degraded_queue"],
    "affected_paths": ["scripts/e2e_test.py", "common/status_store.py"],
    "risk_level": "medium"
  },
  "source": {
    "mode": "mcp",
    "available": true
  }
}
```

## Minimal Operational Rules

- GitNexus must be optional. Any adapter failure should degrade to `available=false`, not break the main workflow.
- Existing status and handoff flow keeps priority over GitNexus output.
- Code intelligence artifacts must be concise and machine-readable.
- Recovery logic runs before enrichment logic.

## Initial Success Criteria

The integration is successful when all of the following are true:

1. A developer can ask for impact analysis before changing code.
2. Selected failures produce a compact code-impact artifact.
3. Handoff can reference code hotspots when present.
4. No existing health or e2e flow regresses when GitNexus is missing.

## Implementation Order

1. Add the adapter interface.
2. Add a no-op fallback adapter.
3. Add one manual CLI path for local testing.
4. Add one failure-enrichment write path.
5. Add one status shard.
6. Add handoff consumption only after the status artifact is stable.
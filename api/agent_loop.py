from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

TAG_MEMORY = "GOLEM_MEMORY"
TAG_ACTION = "GOLEM_ACTION"
TAG_REPLY = "GOLEM_REPLY"


def _extract_tag_block(raw: str, tag: str) -> str:
    exact_pattern = rf"\[{tag}\]([\s\S]*?)\[/{tag}\]"
    exact_match = re.search(exact_pattern, raw, flags=re.IGNORECASE)
    if exact_match:
        return exact_match.group(1).strip()

    fallback_pattern = rf"\[{tag}\]([\s\S]*?)(?=\[GOLEM_MEMORY\]|\[GOLEM_ACTION\]|\[GOLEM_REPLY\]|$)"
    fallback_match = re.search(fallback_pattern, raw, flags=re.IGNORECASE)
    return fallback_match.group(1).strip() if fallback_match else ""


def _extract_actions(action_block: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if not action_block or action_block.lower() == "null":
        return [], warnings

    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", action_block).replace("```", "").strip()
    if not cleaned:
        return [], warnings

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)], warnings
        if isinstance(parsed, dict):
            steps = parsed.get("steps")
            if isinstance(steps, list):
                return [item for item in steps if isinstance(item, dict)], warnings
            return [parsed], warnings
    except Exception as exc:
        warnings.append(f"action_json_parse_failed: {exc}")

    fallback = re.search(r"\[[\s\S]*\]", cleaned)
    if fallback:
        try:
            parsed = json.loads(fallback.group(0))
            if isinstance(parsed, list):
                warnings.append("action_json_recovered_by_fallback")
                return [item for item in parsed if isinstance(item, dict)], warnings
        except Exception:
            pass

    return [], warnings


def parse_golem_protocol(raw_response: str) -> dict[str, Any]:
    raw = raw_response or ""
    memory = _extract_tag_block(raw, TAG_MEMORY)
    action_block = _extract_tag_block(raw, TAG_ACTION)
    reply = _extract_tag_block(raw, TAG_REPLY)
    actions, warnings = _extract_actions(action_block)

    if not memory and not actions and not reply:
        fallback_reply = raw.strip()
        reply = fallback_reply if fallback_reply else "No reply content"
        warnings.append("no_protocol_tags_detected_fallback_reply")

    return {
        "memory": memory if memory and memory.lower() != "null" else "",
        "actions": actions,
        "reply": reply,
        "warnings": warnings,
    }


async def dispatch_actions(actions: list[dict[str, Any]], backend: Any) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []

    for action in actions:
        name = str(action.get("action", "")).strip().lower()
        try:
            if name in {"query", "query_memory"}:
                q = str(action.get("q") or action.get("query") or "").strip()
                mode = str(action.get("mode") or "hybrid")
                result = await backend.query_memory(q, mode)
            elif name in {"ingest", "ingest_memory"}:
                content = str(action.get("content") or "").strip()
                mem_type = str(action.get("mem_type") or "verified_truth")
                title = str(action.get("title") or "")
                result = await backend.ingest_memory(content, mem_type, title)
            elif name in {"log_error", "error"}:
                result = await backend.log_error(
                    root_cause=str(action.get("root_cause") or "unspecified"),
                    solution=str(action.get("solution") or "unspecified"),
                    topic=str(action.get("topic") or ""),
                    context=str(action.get("context") or ""),
                )
            elif name in {"rules", "get_rules"}:
                category = str(action.get("category") or "all")
                result = backend.get_rules(category)
            else:
                observations.append(
                    {
                        "action": name or "unknown",
                        "ok": False,
                        "error": "unsupported_action",
                    }
                )
                continue

            observations.append(
                {
                    "action": name,
                    "ok": True,
                    "result": result,
                }
            )
        except Exception as exc:
            observations.append(
                {
                    "action": name or "unknown",
                    "ok": False,
                    "error": str(exc),
                }
            )

    return observations


async def run_protocol_loop(
    user_input: str,
    raw_response: str,
    backend: Any,
    persist_memory: bool = True,
    execute_actions: bool = True,
) -> dict[str, Any]:
    parsed = parse_golem_protocol(raw_response)
    observations: list[dict[str, Any]] = []

    if persist_memory and parsed["memory"]:
        result = await backend.ingest_memory(parsed["memory"], "verified_truth", "protocol-memory")
        observations.append({"action": "protocol_memory_ingest", "ok": result.startswith("✅"), "result": result})

    if execute_actions and parsed["actions"]:
        action_observations = await dispatch_actions(parsed["actions"], backend)
        observations.extend(action_observations)

    return {
        "ok": True,
        "user_input": user_input,
        "parsed": parsed,
        "observation": observations,
        "next_prompt": {
            "text": "[System Observation]\n" + json.dumps(observations, ensure_ascii=False, indent=2),
            "hint": "Use this observation for the next model turn.",
        },
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

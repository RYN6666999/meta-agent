#!/usr/bin/env python3
"""Minimal Toolbox MCP server for tool inventory and guarded execution."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

BASE = Path('/Users/ryan/meta-agent')
MEMORY_DIR = BASE / 'memory'

TOOL_REGISTRY: dict[str, dict[str, str]] = {
    'toolbox-health': {'command': 'bash /Users/ryan/meta-agent/scripts/toolbox/toolbox-health.sh'},
    'douyin-preflight': {'command': 'bash /Users/ryan/meta-agent/scripts/toolbox/douyin-preflight.sh'},
    'toolbox-prune': {'command': 'python3 /Users/ryan/meta-agent/scripts/toolbox/toolbox-prune.py'},
    'toolbox-open': {'command': 'bash /Users/ryan/meta-agent/scripts/toolbox/toolbox-open.sh'},
}

mcp = FastMCP('toolbox-mcp')


def _run(cmd: str, timeout_sec: int = 30) -> dict[str, Any]:
    proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout_sec, check=False)
    return {
        'ok': proc.returncode == 0,
        'returncode': proc.returncode,
        'stdout': proc.stdout[-4000:],
        'stderr': proc.stderr[-4000:],
    }


@mcp.tool
def list_tools() -> dict[str, Any]:
    return {'tools': sorted(list(TOOL_REGISTRY.keys()))}


@mcp.tool
def check_tool(name: str) -> dict[str, Any]:
    if name not in TOOL_REGISTRY:
        return {'ok': False, 'error': f'unknown tool: {name}'}
    return _run(TOOL_REGISTRY[name]['command'])


@mcp.tool
def run_tool(name: str) -> dict[str, Any]:
    if name not in TOOL_REGISTRY:
        return {'ok': False, 'error': f'unknown tool: {name}'}
    return _run(TOOL_REGISTRY[name]['command'])


@mcp.tool
def record_result(name: str, payload: str) -> dict[str, Any]:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    out = MEMORY_DIR / f'toolbox-mcp-{name}.json'
    try:
        data = json.loads(payload)
    except Exception:
        data = {'raw': payload}
    data['recorded_at'] = now
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'ok': True, 'path': str(out)}


if __name__ == '__main__':
    mcp.run()

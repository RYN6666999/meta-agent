#!/usr/bin/env python3
"""Toolbox local runner: provide guarded HTTP endpoints for UI button execution."""

from __future__ import annotations

import subprocess
import time
import socket
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


BASE = Path('/Users/ryan/meta-agent')
LOG_DIR = Path('/tmp') / 'toolbox-runner-logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)


class ActionDef(BaseModel):
	cmd: str
	cwd: str | None = None
	long_running: bool = False
	timeout_sec: int = 120


REGISTRY: dict[str, dict[str, ActionDef]] = {
	'toolbox-health': {
		'run': ActionDef(cmd='bash scripts/toolbox/toolbox-health.sh', cwd=str(BASE)),
	},
	'douyin-preflight': {
		'run': ActionDef(cmd='bash scripts/toolbox/douyin-preflight.sh', cwd=str(BASE)),
	},
	'toolbox-prune': {
		'run': ActionDef(cmd='python3 scripts/toolbox/toolbox-prune.py', cwd=str(BASE)),
	},
	'sync-status': {
		'run': ActionDef(cmd='bash scripts/toolbox/sync-status-to-ui.sh', cwd=str(BASE)),
	},
	'toolbox-full-cycle': {
		'run': ActionDef(
			cmd=(
				'bash scripts/toolbox/toolbox-health.sh && '
				'bash scripts/toolbox/douyin-preflight.sh && '
				'python3 scripts/toolbox/toolbox-prune.py && '
				'bash scripts/toolbox/sync-status-to-ui.sh'
			),
			cwd=str(BASE),
			timeout_sec=180,
		),
	},
	'decision-engine': {
		'run': ActionDef(cmd='python3 scripts/decision-engine.py', cwd=str(BASE)),
	},
	'health-check': {
		'run': ActionDef(cmd='python3 scripts/health_check.py', cwd=str(BASE)),
	},
	'e2e': {
		'run': ActionDef(cmd='python3 scripts/e2e_test.py', cwd=str(BASE), timeout_sec=240),
	},
	'truth-xval': {
		'run': ActionDef(cmd='python3 scripts/truth-xval.py', cwd=str(BASE)),
	},
	'memory-mcp': {
		'run': ActionDef(cmd='python3 tools/memory-mcp/server.py', cwd=str(BASE), long_running=True),
	},
	'agent-status': {
		'run': ActionDef(cmd='tools/agent-ssh-gateway/host/bin/agent-status', cwd=str(BASE)),
	},
	'agent-switch': {
		'run': ActionDef(cmd='tools/agent-ssh-gateway/host/bin/agent-switch on', cwd=str(BASE)),
	},
	'novel-server': {
		'run': ActionDef(cmd='python3 server.py', cwd=str(BASE / 'tools/novel-framework-analyzer'), long_running=True),
		'open_ui': ActionDef(cmd='open http://localhost:8765/#upload', cwd=str(BASE)),
	},
	'novel-batch': {
		'run': ActionDef(
			cmd='python3 tools/novel-framework-analyzer/scripts/batch_analyze.py --chapters 1-3 --skip-existing',
			cwd=str(BASE),
			timeout_sec=300,
		),
	},
	'toolbox-console-dev': {
		'run': ActionDef(cmd='npm --prefix scripts/toolbox-console run dev', cwd=str(BASE), long_running=True),
		'open_ui': ActionDef(cmd='open http://localhost:5173', cwd=str(BASE)),
	},
	'douyin-sender': {
		'run': ActionDef(cmd='python3 /Users/ryan/Desktop/douyin_sender.py', cwd=str(BASE), long_running=True),
	},
	'douyin-cookie-refresh': {
		'run': ActionDef(cmd='python3 /Users/ryan/Projects/n8n/scripts/refresh_douyin_cookie.py', cwd=str(BASE)),
	},
}


class RunRequest(BaseModel):
	tool_id: str
	action: str = 'run'


app = FastAPI(title='Toolbox Runner')
app.add_middleware(
	CORSMiddleware,
	allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
	allow_methods=['*'],
	allow_headers=['*'],
)


def _run_once(action: ActionDef) -> dict[str, Any]:
	proc = subprocess.run(
		action.cmd,
		shell=True,
		cwd=action.cwd,
		text=True,
		capture_output=True,
		timeout=action.timeout_sec,
		check=False,
	)
	return {
		'ok': proc.returncode == 0,
		'returncode': proc.returncode,
		'stdout': proc.stdout[-5000:],
		'stderr': proc.stderr[-5000:],
	}


def _run_background(tool_id: str, action_name: str, action: ActionDef) -> dict[str, Any]:
	log_path = LOG_DIR / f'{tool_id}-{action_name}.log'
	log_file = open(log_path, 'a', encoding='utf-8')
	proc = subprocess.Popen(
		action.cmd,
		shell=True,
		cwd=action.cwd,
		text=True,
		stdout=log_file,
		stderr=log_file,
		start_new_session=True,
	)
	return {
		'ok': True,
		'pid': proc.pid,
		'stdout': f'Background process started for {tool_id}:{action_name}',
		'stderr': '',
		'log_path': str(log_path),
	}


def _port_open(host: str, port: int) -> bool:
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.settimeout(0.5)
		return sock.connect_ex((host, port)) == 0


@app.get('/health')
def health() -> dict[str, Any]:
	return {'ok': True, 'service': 'toolbox-runner'}


@app.post('/run')
def run_tool(req: RunRequest) -> dict[str, Any]:
	tool_actions = REGISTRY.get(req.tool_id)
	if not tool_actions:
		raise HTTPException(404, f'Unknown tool_id: {req.tool_id}')

	action = tool_actions.get(req.action)
	if not action:
		raise HTTPException(404, f'Unknown action for {req.tool_id}: {req.action}')

	# One-click UX for novel UI: auto-start backend service if needed, then open page.
	if req.tool_id == 'novel-server' and req.action == 'open_ui':
		started_service = False
		if not _port_open('127.0.0.1', 8765):
			run_action = tool_actions.get('run')
			if run_action is None:
				raise HTTPException(500, 'novel-server missing run action')
			_run_background(req.tool_id, 'run', run_action)
			started_service = True
			time.sleep(1.0)
		opened = _run_once(action)
		opened['started_service'] = started_service
		return opened

	if action.long_running:
		return _run_background(req.tool_id, req.action, action)
	return _run_once(action)


if __name__ == '__main__':
	import uvicorn

	print('Toolbox runner listening on http://127.0.0.1:8766')
	uvicorn.run(app, host='127.0.0.1', port=8766, reload=False)

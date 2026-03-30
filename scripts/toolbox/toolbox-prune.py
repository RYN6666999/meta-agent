#!/usr/bin/env python3
"""Generate prune suggestions for toolbox tools without mutating source files."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path('/Users/ryan/meta-agent')
OUT = BASE / 'memory' / 'toolbox-prune-report.json'

TOOL_PORTS = {
    'toolbox-console-dev': 5188,
    'novel-server': 8765,
    'douyin-sender': 5678,
    'douyin-cookie-refresh': 8000,
}

def port_up(port: int) -> bool:
    cmd = ['lsof', f'-iTCP:{port}', '-sTCP:LISTEN']
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return res.returncode == 0

report: dict[str, object] = {
    'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'policy': 'suggest-hide-if-critical-dependency-down',
    'candidates': [],
    'keep': [],
}

for tool_id, port in TOOL_PORTS.items():
    ok = port_up(port)
    entry = {
        'tool_id': tool_id,
        'critical_dependency': f'localhost:{port}',
        'dependency_up': ok,
    }
    if ok:
        cast_keep = report['keep']
        assert isinstance(cast_keep, list)
        cast_keep.append(entry)
    else:
        cast_cand = report['candidates']
        assert isinstance(cast_cand, list)
        cast_cand.append(entry)

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Wrote {OUT}')
print(json.dumps(report, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.code_intelligence import CodeIntelRequest, get_code_intelligence_adapter, serialize_code_intel_result


def main() -> int:
    adapter = get_code_intelligence_adapter(working_dir=ROOT_DIR)
    payload: dict[str, object] = {
        'adapter_available': adapter.is_available(),
        'provider': adapter.__class__.__name__,
    }

    if adapter.is_available():
        overview = adapter.overview(CodeIntelRequest(kind='overview', repo='meta-agent'))
        payload['overview'] = serialize_code_intel_result(overview)

        impact = adapter.impact(
            CodeIntelRequest(
                kind='impact',
                target='run_protocol_loop',
                repo='meta-agent',
                metadata={'direction': 'upstream'},
            )
        )
        payload['impact'] = serialize_code_intel_result(impact)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
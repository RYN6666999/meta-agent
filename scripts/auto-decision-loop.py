#!/usr/bin/env python3
"""auto-decision-loop.py — 簡化版自動決策循環。

單一流程：decision-engine --execute，並寫入執行日誌。
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent.parent
DECISION_ENGINE = BASE_DIR / "scripts" / "decision-engine.py"
LATEST_HANDOFF = BASE_DIR / "memory" / "handoff" / "latest-handoff.md"
AUTO_DECISION_LOG = BASE_DIR / "memory" / "auto-decision-log.md"


def run_decision_loop() -> dict[str, Any]:
    """執行完整的決策循環"""

    print("[auto-decision-loop] 開始決策循環...")
    timestamp = datetime.now().isoformat()

    # Step 1: 執行決策引擎（含自動執行）
    print("[auto-decision-loop] 1️⃣  分析並執行事實面決策...")
    try:
        engine_output = subprocess.run(
            ["python3", str(DECISION_ENGINE), "--execute", "--json"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if engine_output.returncode != 0:
            print(f"❌ 決策引擎錯誤：{engine_output.stderr[:200]}")
            return {"success": False, "error": "decision_engine_failed"}
        engine_json = {}
        try:
            engine_json = json.loads(engine_output.stdout or "{}")
        except Exception:
            engine_json = {
                "parse_error": True,
                "stdout_preview": (engine_output.stdout or "")[:300],
            }
    except Exception as e:
        print(f"❌ 執行決策引擎失敗：{e}")
        return {"success": False, "error": str(e)}

    # Step 3: 記錄到日誌
    log_entry = f"""
---
timestamp: {timestamp}
decision_engine_output: OK
workflow_status: SIMPLIFIED
---

**決策循環executed at {timestamp}**

通常流程：
- 讀取事實（health/e2e/git/error-log）
- 規則化分析
- 自動執行可自動項目
- 寫回 machine-readable 報告

每小時由 launchd 自動觸發。
"""

    if AUTO_DECISION_LOG.exists():
        log_entry = AUTO_DECISION_LOG.read_text() + "\n" + log_entry
    AUTO_DECISION_LOG.write_text(log_entry, encoding="utf-8")

    # Step 4: 更新 latest-handoff.md 的元數據
    if LATEST_HANDOFF.exists():
        content = LATEST_HANDOFF.read_text(encoding="utf-8")
        # 簡單替換生成時間戳
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("generated:"):
                lines[i] = f"generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        LATEST_HANDOFF.write_text("\n".join(lines), encoding="utf-8")

    print("[auto-decision-loop] ✅ 決策循環完成")
    return {
        "success": True,
        "timestamp": timestamp,
        "decision_engine": "OK",
        "workflow": "SIMPLIFIED",
        "decision_payload": engine_json,
    }


if __name__ == "__main__":
    result = run_decision_loop()
    print(json.dumps(result, indent=2, ensure_ascii=False))

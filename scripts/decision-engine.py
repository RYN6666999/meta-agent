#!/usr/bin/env python3
"""
decision-engine.py — 事實面決策引擎（簡化迴圈版）

目標：
- 單一入口，讀取可驗證事實
- 規則化決策（非 LLM 建議）
- 可選自動執行
- 每次執行都寫入 machine-readable 報告，方便下一輪迭代
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.decision_rule_engine import DecisionRuleEngine

BASE_DIR = ROOT_DIR
SYSTEM_STATUS = BASE_DIR / "memory" / "system-status.json"
ERROR_LOG_DIR = BASE_DIR / "error-log"
SMOKE_REPORT = BASE_DIR / "memory" / "smoke-run-report.json"
LOOP_REPORT = BASE_DIR / "memory" / "decision-loop-last.json"

ACTION_TO_SCRIPTS: dict[str, list[str]] = {
    "run_truth_xval": ["scripts/truth-xval.py"],
    "reactivate_webhooks_and_xval": ["scripts/reactivate_webhooks.py", "scripts/truth-xval.py"],
    "check_git_score_and_commit": ["scripts/git-score.py"],
    "review_and_fix_violation": [],
}


class DecisionContext:
    """決策上下文：蒐集當前事實。"""

    def __init__(self) -> None:
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.system_status = self._load_json(SYSTEM_STATUS)
        self.git_status = self._get_git_status()
        self.recent_errors = self._get_recent_error_names()
        self.smoke_report = self._load_json(SMOKE_REPORT)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _get_git_status(self) -> dict[str, Any]:
        try:
            uncommitted_output = subprocess.run(
                ["git", "-C", str(BASE_DIR), "diff", "--name-only"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            ).stdout.strip()
            uncommitted = [line for line in uncommitted_output.split("\n") if line.strip()]

            return {
                "uncommitted_count": len(uncommitted),
                "uncommitted_files": uncommitted,
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _get_recent_error_names(self) -> list[str]:
        if not ERROR_LOG_DIR.exists():
            return []
        files = sorted(ERROR_LOG_DIR.glob("*.md"), reverse=True)[:5]
        return [f.name for f in files]

    def as_rule_context(self) -> dict[str, Any]:
        return {
            "health_check": self.system_status.get("health_check", {}),
            "e2e_memory_extract": self.system_status.get("e2e_memory_extract", {}),
            "git_status": self.git_status,
            "recent_errors": self.recent_errors,
            "smoke_run": self.smoke_report,
        }


class DecisionEngine:
    """規則化決策引擎。"""

    def __init__(self, ctx: DecisionContext) -> None:
        self.ctx = ctx
        self.rule_engine = DecisionRuleEngine()

    def analyze(self) -> list[dict[str, Any]]:
        decisions = self.rule_engine.evaluate_rules(self.ctx.as_rule_context())
        for d in decisions:
            action = d.get("action", "")
            d["scripts"] = ACTION_TO_SCRIPTS.get(action, [])
            d["facts"] = {
                "health_ok": self.ctx.system_status.get("health_check", {}).get("ok"),
                "e2e_ok": self.ctx.system_status.get("e2e_memory_extract", {}).get("ok"),
                "uncommitted_count": self.ctx.git_status.get("uncommitted_count", 0),
            }
        return decisions


class DecisionExecutor:
    """依決策執行腳本。"""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def execute(self, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for decision in decisions:
            action = decision.get("action", "unknown")
            scripts = decision.get("scripts", [])
            auto = bool(decision.get("auto_executable"))

            if not auto:
                results.append({
                    "action": action,
                    "executed": False,
                    "ok": False,
                    "reason": "manual_required",
                })
                continue

            if not scripts:
                results.append({
                    "action": action,
                    "executed": False,
                    "ok": False,
                    "reason": "no_script_mapped",
                })
                continue

            action_ok = True
            step_outputs: list[dict[str, Any]] = []
            for script in scripts:
                script_path = self.root_dir / script
                if not script_path.exists():
                    action_ok = False
                    step_outputs.append({
                        "script": script,
                        "ok": False,
                        "returncode": -1,
                        "output": "script_not_found",
                    })
                    continue

                proc = subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=str(self.root_dir),
                    capture_output=True,
                    text=True,
                    timeout=360,
                    check=False,
                )
                output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[:500]
                step_ok = proc.returncode == 0
                if not step_ok:
                    action_ok = False
                step_outputs.append({
                    "script": script,
                    "ok": step_ok,
                    "returncode": proc.returncode,
                    "output": output,
                })

            results.append({
                "action": action,
                "executed": True,
                "ok": action_ok,
                "steps": step_outputs,
            })

        return results


def save_loop_report(ctx: DecisionContext, decisions: list[dict[str, Any]], executions: list[dict[str, Any]], execute_mode: bool) -> None:
    report = {
        "checked_at": ctx.timestamp,
        "mode": "execute" if execute_mode else "analyze",
        "facts": ctx.as_rule_context(),
        "decisions": decisions,
        "executions": executions,
        "next_iteration_hint": "Re-run this script after health/e2e or source changes.",
    }
    LOOP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LOOP_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(decisions: list[dict[str, Any]], executions: list[dict[str, Any]], execute_mode: bool) -> None:
    print("=" * 70)
    print("Decision Engine (Fact-Driven)")
    print("=" * 70)
    print(f"mode: {'execute' if execute_mode else 'analyze'}")
    print(f"decisions: {len(decisions)}")

    if not decisions:
        print("- no action triggered")

    for idx, d in enumerate(decisions, start=1):
        priority = d.get("priority", "P?")
        action = d.get("action", "unknown")
        reason = d.get("reason", "")
        auto = "auto" if d.get("auto_executable") else "manual"
        print(f"{idx}. [{priority}] {action} ({auto}) - {reason}")

    if execute_mode:
        ok_count = sum(1 for e in executions if e.get("ok"))
        print(f"executed_ok: {ok_count}/{len(executions)}")

    print(f"report: {LOOP_REPORT}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fact-driven decision engine")
    parser.add_argument("--execute", action="store_true", help="execute auto-executable decisions")
    parser.add_argument("--json", action="store_true", help="print JSON decisions to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = DecisionContext()
    engine = DecisionEngine(ctx)
    decisions = engine.analyze()

    executions: list[dict[str, Any]] = []
    if args.execute:
        executions = DecisionExecutor(BASE_DIR).execute(decisions)

    save_loop_report(ctx, decisions, executions, execute_mode=args.execute)

    if args.json:
        print(json.dumps({"decisions": decisions, "executions": executions}, ensure_ascii=False, indent=2))
    else:
        print_summary(decisions, executions, execute_mode=args.execute)

    if args.execute and any(e.get("executed") and not e.get("ok") for e in executions):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

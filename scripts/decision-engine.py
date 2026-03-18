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
HANDOFF_FILE = BASE_DIR / "memory" / "handoff" / "latest-handoff.md"
DEDUP_LOG = BASE_DIR / "memory" / "dedup-log.md"
FORUM_SIGNALS = BASE_DIR / "memory" / "forum-signals.json"

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
        self.fact_bundle = self._build_fact_bundle()

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
        return None

    @staticmethod
    def _freshness_from_time(checked_at: str | None, fresh_minutes: int = 15) -> str:
        dt = DecisionContext._parse_time(checked_at)
        if not dt:
            return "unknown"
        delta_minutes = (datetime.now() - dt).total_seconds() / 60
        return "fresh" if delta_minutes <= fresh_minutes else "stale"

    @staticmethod
    def _fact_entry(value: Any, freshness: str, confidence: str) -> dict[str, Any]:
        return {
            "value": value,
            "freshness": freshness,
            "confidence": confidence,
        }

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

    def _get_recent_error_summary(self) -> dict[str, Any]:
        if not ERROR_LOG_DIR.exists():
            return {"count": 0, "p0_like": 0, "p1_like": 0, "files": []}
        files = sorted(ERROR_LOG_DIR.glob("*.md"), reverse=True)[:5]
        p0_like = 0
        p1_like = 0
        names: list[str] = []
        for f in files:
            names.append(f.name)
            try:
                content = f.read_text(encoding="utf-8")[:800].lower()
                if any(k in content for k in ("critical", "p0", "全掛", "完全失敗")):
                    p0_like += 1
                elif any(k in content for k in ("error", "p1", "失敗", "timeout")):
                    p1_like += 1
            except Exception:
                continue
        return {
            "count": len(files),
            "p0_like": p0_like,
            "p1_like": p1_like,
            "files": names,
        }

    def _get_handoff_summary(self) -> dict[str, Any]:
        if not HANDOFF_FILE.exists():
            return {"exists": False, "top_gaps": []}
        try:
            text = HANDOFF_FILE.read_text(encoding="utf-8")
        except Exception:
            return {"exists": False, "top_gaps": []}

        top_gaps: list[str] = []
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("1. ") or s.startswith("2. ") or s.startswith("3. "):
                top_gaps.append(s)
            if len(top_gaps) >= 3:
                break

        return {
            "exists": True,
            "top_gaps": top_gaps,
            "line_count": len(text.splitlines()),
        }

    def _get_github_summary(self) -> dict[str, Any]:
        try:
            branch = subprocess.run(
                ["git", "-C", str(BASE_DIR), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            ).stdout.strip()
            commits = subprocess.run(
                ["git", "-C", str(BASE_DIR), "log", "--oneline", "-n", "5"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip().splitlines()
            return {
                "branch": branch,
                "recent_commits": commits,
                "recent_commit_count": len([c for c in commits if c.strip()]),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _get_forum_summary(self) -> dict[str, Any]:
        data = self._load_json(FORUM_SIGNALS)
        if not data:
            return {
                "enabled": False,
                "note": "forum_signals_missing_or_empty",
            }
        return {
            "enabled": True,
            "keys": sorted(data.keys()),
            "signal_count": len(data) if isinstance(data, dict) else 0,
        }

    def _get_graph_exposure_summary(self) -> dict[str, Any]:
        truth_count = len(list((BASE_DIR / "truth-source").glob("*.md"))) if (BASE_DIR / "truth-source").exists() else 0
        dedup_exists = DEDUP_LOG.exists()
        dedup_preview = ""
        if dedup_exists:
            try:
                dedup_preview = DEDUP_LOG.read_text(encoding="utf-8")[:160]
            except Exception:
                dedup_preview = ""
        return {
            "truth_source_docs": truth_count,
            "dedup_log_exists": dedup_exists,
            "dedup_preview": dedup_preview,
        }

    def _build_fact_bundle(self) -> dict[str, Any]:
        checked_at = self.system_status.get("health_check", {}).get("checked_at")
        health_freshness = self._freshness_from_time(checked_at, fresh_minutes=15)
        smoke_checked_at = self.smoke_report.get("checked_at") if isinstance(self.smoke_report, dict) else None
        smoke_freshness = self._freshness_from_time(smoke_checked_at, fresh_minutes=30)

        return {
            "github": self._fact_entry(self._get_github_summary(), "fresh", "high"),
            "handoff": self._fact_entry(self._get_handoff_summary(), "fresh", "medium"),
            "error_library": self._fact_entry(self._get_recent_error_summary(), "fresh", "high"),
            "detection_results": self._fact_entry(
                {
                    "health_check": self.system_status.get("health_check", {}),
                    "e2e_memory_extract": self.system_status.get("e2e_memory_extract", {}),
                    "smoke_run": self.smoke_report,
                },
                "fresh" if health_freshness == "fresh" and smoke_freshness in ("fresh", "unknown") else "stale",
                "high",
            ),
            "graph_exposure": self._fact_entry(self._get_graph_exposure_summary(), "fresh", "medium"),
            "forum": self._fact_entry(
                self._get_forum_summary(),
                "fresh" if FORUM_SIGNALS.exists() else "unknown",
                "low" if not FORUM_SIGNALS.exists() else "medium",
            ),
        }

    def as_rule_context(self) -> dict[str, Any]:
        return {
            "health_check": self.system_status.get("health_check", {}),
            "e2e_memory_extract": self.system_status.get("e2e_memory_extract", {}),
            "git_status": self.git_status,
            "recent_errors": self.recent_errors,
            "smoke_run": self.smoke_report,
            "fact_bundle": self.fact_bundle,
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

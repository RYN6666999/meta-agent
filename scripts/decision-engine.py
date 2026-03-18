#!/usr/bin/env python3
"""
decision-engine.py — 事實面決策自動化

根據當前系統事實（health 狀態、git diff、錯誤日誌），
自動決定下一步應該做什麼，消除 Ryan 的決策壓力。

核心原則：
- 事實面為準（測量數據，不是生成式建議）
- 明確的下一步（已就緒，手工確認即執行）
- 機器決策（基於規則引擎，不是 LLM 的「可以考慮」）

輸出：更新 latest-handoff.md 的 next_steps（事實面驅動）
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

BASE_DIR = Path(__file__).parent.parent
LAW_JSON = BASE_DIR / "law.json"
SYSTEM_STATUS = BASE_DIR / "memory" / "system-status.json"
LATEST_HANDOFF = BASE_DIR / "memory" / "handoff" / "latest-handoff.md"
ERROR_LOG_DIR = BASE_DIR / "error-log"
GIT_SCORE_LOG = BASE_DIR / "memory" / "git-score-log.md"


class DecisionContext:
    """決策上下文 — 蒐集所有事實面數據"""

    def __init__(self):
        self.law = self._load_json(LAW_JSON)
        self.system_status = self._load_json(SYSTEM_STATUS)
        self.git_status = self._get_git_status()
        self.recent_errors = self._get_recent_errors()
        self.health_state = self._parse_health_state()
        self.e2e_state = self._parse_e2e_state()
        self.timestamp = datetime.now().isoformat()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _get_git_status(self) -> dict[str, Any]:
        """取得 git 當前狀態"""
        try:
            # 未 commit 的改動
            output = subprocess.run(
                ["git", "-C", str(BASE_DIR), "diff", "--name-only"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            uncommitted = output.split("\n") if output else []

            # 未推送的 commit
            output = subprocess.run(
                ["git", "-C", str(BASE_DIR), "log", "--oneline", "origin/main..HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            unpushed = len(output.split("\n")) if output else 0

            return {
                "uncommitted_files": uncommitted,
                "uncommitted_count": len(uncommitted),
                "unpushed_commits": unpushed,
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_recent_errors(self) -> list[dict[str, Any]]:
        """取得最近 3 個 error-log"""
        if not ERROR_LOG_DIR.exists():
            return []
        files = sorted(ERROR_LOG_DIR.glob("*.md"), reverse=True)[:3]
        return [{"filename": f.name, "path": str(f)} for f in files]

    def _parse_health_state(self) -> dict[str, Any]:
        """解析 health_check 狀態"""
        status = self.system_status.get("health_check", {})
        return {
            "ok": status.get("ok", False),
            "passed_at": status.get("passed_at"),
            "failed_at": status.get("failed_at"),
        }

    def _parse_e2e_state(self) -> dict[str, Any]:
        """解析 e2e 狀態"""
        status = self.system_status.get("e2e_memory_extract", {})
        return {
            "ok": status.get("ok", False),
            "passed_at": status.get("passed_at"),
            "failed_at": status.get("failed_at"),
        }


class DecisionEngine:
    """決策引擎 — 根據事實面規則自動決定下一步"""

    def __init__(self, ctx: DecisionContext):
        self.ctx = ctx
        self.decisions: list[dict[str, Any]] = []

    def analyze(self) -> list[dict[str, Any]]:
        """執行決策分析"""
        self._check_health_recovery()
        self._check_rule_violations()
        self._check_git_threshold()
        self._check_phase_transition()
        self._prioritize_decisions()
        return self.decisions

    def _check_health_recovery(self) -> None:
        """檢查 health/e2e 的自動恢復機制

        根據 law.json 的規則：
        - health 失敗 → 自動觸發交叉查核 (truth-xval)
        - e2e 失敗 → 自動觸發 reactivate-webhooks + truth-xval
        """
        health_ok = self.ctx.health_state.get("ok", False)
        e2e_ok = self.ctx.e2e_state.get("ok", False)

        if not health_ok:
            self.decisions.append({
                "id": "recovery_health_xval",
                "priority": "P0",
                "action": "run_truth_xval",
                "reason": "health_check 失敗，自動觸發交叉查核",
                "evidence": f"health_check.failed_at = {self.ctx.health_state.get('failed_at')}",
                "script": "scripts/truth-xval.py",
                "auto_executable": True,
            })

        if not e2e_ok:
            self.decisions.append({
                "id": "recovery_e2e_webhooks",
                "priority": "P0",
                "action": "reactivate_webhooks_and_xval",
                "reason": "e2e_memory_extract 失敗，自動觸發 webhook 重啟 + 交叉查核",
                "evidence": f"e2e_memory_extract.failed_at = {self.ctx.e2e_state.get('failed_at')}",
                "scripts": [
                    "scripts/reactivate-webhooks.py",
                    "scripts/truth-xval.py",
                ],
                "auto_executable": True,
            })

    def _check_rule_violations(self) -> None:
        """檢查 law.json 的 forbidden 規則是否被違反

        根據最近的 error-log，判斷是否有規則違反
        """
        recent_errors = self.ctx.recent_errors[:3]
        if not recent_errors:
            return

        # 檢查最新的 error-log
        latest_error = recent_errors[0]["filename"]
        error_topics = [
            ("bug_closeout", "bug 修復需要立即 log_error"),
            ("webhook", "n8n webhook 相關規則"),
            ("health_check", "health 失敗相關規則"),
        ]

        for topic, description in error_topics:
            if topic in latest_error.lower():
                self.decisions.append({
                    "id": f"rule_violation_{topic}",
                    "priority": "P0" if topic == "bug_closeout" else "P1",
                    "action": "review_and_fix_violation",
                    "reason": description,
                    "evidence": f"error-log/{latest_error}",
                    "requires_manual_review": True,
                })

    def _check_git_threshold(self) -> None:
        """檢查 git diff 是否超過自動竝交的閾值

        law.json git_score.threshold = 50
        """
        if self.ctx.git_status.get("error"):
            return

        uncommitted_count = self.ctx.git_status.get("uncommitted_count", 0)
        if uncommitted_count > 0:
            self.decisions.append({
                "id": "git_pending_changes",
                "priority": "P1",
                "action": "check_git_score_and_commit",
                "reason": f"有 {uncommitted_count} 個未提交文件",
                "evidence": self.ctx.git_status.get("uncommitted_files", [])[:5],
                "script": "scripts/git-score.py",
                "auto_executable": True,
            })

    def _check_phase_transition(self) -> None:
        """檢查是否可以進入下一個 Phase

        Phase 流程（law.json workflow_loop）：
        - Phase 1: JSON 施工圖，禁止執行 ✅ (已完成 Phase 1: razor-first)
        - Phase 2: 解鎖 MCP，Just-in-Time RAG
        - Phase 3: 驗證通過 → truth-source + LightRAG
        """
        # 檢查是否有新的 phase 就緒
        if "5beb41c" in subprocess.run(
            ["git", "-C", str(BASE_DIR), "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
        ).stdout:
            # Phase 1 剛完成
            self.decisions.append({
                "id": "phase2_ready",
                "priority": "P0",
                "action": "start_phase2_state_machine",
                "reason": "Phase 1 (razor-first RequestContext) 已完成，Phase 2 (狀態機) 可開始",
                "evidence": "commit 5beb41c: Phase 1 refactoring",
                "next_deliverables": [
                    "State machine 實現 (trigger_checkpoints 邏輯)",
                    "bug-closeout / major-change-guard / kg-maintenance 執行腳本",
                    "統一狀態結構 (phase 3)",
                ],
                "requires_manual_review": True,
            })

    def _prioritize_decisions(self) -> None:
        """按優先級排序決策"""
        priority_map = {"P0": 0, "P1": 1, "P2": 2}
        self.decisions.sort(
            key=lambda d: (
                priority_map.get(d.get("priority", "P2"), 3),
                d.get("id", ""),
            )
        )


def render_handoff_section(decisions: list[dict[str, Any]]) -> str:
    """將決策轉換為 handoff markdown 格式"""
    if not decisions:
        return "## 下一步\n無待決事項\n"

    lines = ["## 下一步（機器決策，事實面驅動）\n"]

    for idx, decision in enumerate(decisions, 1):
        priority = decision.get("priority", "P?")
        action = decision.get("action", "unknown")
        reason = decision.get("reason", "")
        evidence = decision.get("evidence", "")

        auto = "✓ 自動執行可行" if decision.get("auto_executable") else "⚠ 需手工確認"

        lines.append(f"### {idx}. {action} [{priority}] {auto}")
        lines.append(f"**原因**：{reason}")
        if evidence:
            if isinstance(evidence, list):
                lines.append(f"**證據**：{', '.join(map(str, evidence[:3]))}")
            else:
                lines.append(f"**證據**：{evidence}")

        if decision.get("script"):
            lines.append(f"**執行**：`{decision['script']}`")
        elif decision.get("scripts"):
            for script in decision["scripts"]:
                lines.append(f"**執行**：`{script}`")

        lines.append("")

    return "\n".join(lines)


def main() -> None:
    """主程序"""
    ctx = DecisionContext()
    engine = DecisionEngine(ctx)
    decisions = engine.analyze()

    # 生成 handoff 內容
    handoff_section = render_handoff_section(decisions)

    print("\n" + "=" * 70)
    print("決策自動化結果")
    print("=" * 70)
    print(handoff_section)

    # 更新 latest-handoff.md（可選）
    if LATEST_HANDOFF.exists():
        content = LATEST_HANDOFF.read_text(encoding="utf-8")
        # 簡單替換（在實際應用中應該用更穩健的 markdown 解析）
        # TODO: 更新 handoff 文檔
        pass

    print("\n✅ 決策分析完成")
    print(f"共 {len(decisions)} 個待決事項，按優先級排序")


if __name__ == "__main__":
    main()

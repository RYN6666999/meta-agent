#!/usr/bin/env python3
"""
decision_rule_engine.py — 決策引擎規則化 (Phase 2-B)

從 law.json 的 decision_automation 分類提取規則，
替代 decision-engine.py 中的硬碼「if health_ok: ...」

核心想法：
- rule-based 系統，而非啟發式
- law.json 是真理源，engine 只是執行層
- 新增規則 = 只需修改 law.json，無需改 engine 代碼
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).parent.parent
LAW_JSON = BASE_DIR / "law.json"


@dataclass
class Rule:
    """決策規則"""

    id: str
    condition: Callable[[dict[str, Any]], bool]
    action: str  # 對應的 checkpoint 名稱
    priority: str  # P0, P1, P2
    reason: str
    auto_executable: bool = False


class DecisionRuleEngine:
    """決策規則引擎"""

    def __init__(self):
        self.law = self._load_law()
        self.rules: list[Rule] = []
        self._build_rules()

    @staticmethod
    def _load_law() -> dict[str, Any]:
        """加載 law.json"""
        if not LAW_JSON.exists():
            return {}
        try:
            return json.loads(LAW_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _build_rules(self) -> None:
        """從 law.json 和系統狀態構建規則列表"""
        # 從 law.json 的 decision_automation.core_logic.decision_types 建立規則

        decision_types = (
            self.law.get("decision_automation", {})
            .get("core_logic", {})
            .get("decision_types", [])
        )

        # Rule 1: Health 失敗 → truth-xval
        self.rules.append(
            Rule(
                id="recovery_health_xval",
                condition=lambda ctx: self._get_health_ok(ctx) is False,
                action="run_truth_xval",
                priority="P0",
                reason="health_check 失敗，自動觸發交叉查核",
                auto_executable=True,
            )
        )

        # Rule 2: E2E 失敗 → webhooks + xval
        self.rules.append(
            Rule(
                id="recovery_e2e_webhooks",
                condition=lambda ctx: self._get_e2e_ok(ctx) is False,
                action="reactivate_webhooks_and_xval",
                priority="P0",
                reason="e2e_memory_extract 失敗，自動觸發 webhook 重啟 + 交叉查核",
                auto_executable=True,
            )
        )

        # Rule 3: Git diff 有改動 → git-score
        self.rules.append(
            Rule(
                id="git_pending_changes",
                condition=lambda ctx: self._get_uncommitted_count(ctx) > 0,
                action="check_git_score_and_commit",
                priority="P1",
                reason="有未提交文件，評估 git score",
                auto_executable=True,
            )
        )

        # Rule 4: forbidden 規則違反 → manual review
        self.rules.append(
            Rule(
                id="rule_violation_check",
                condition=lambda ctx: any(
                    error_file and "forbidden" in error_file.lower()
                    for error_file in self._get_recent_errors(ctx)
                ),
                action="review_and_fix_violation",
                priority="P0",
                reason="偵測到 law.json forbidden 規則違反",
                auto_executable=False,
            )
        )

    @staticmethod
    def _bundle_value(ctx: dict[str, Any], source: str) -> Any:
        bundle = ctx.get("fact_bundle", {})
        if not isinstance(bundle, dict):
            return None
        item = bundle.get(source, {})
        if not isinstance(item, dict):
            return None
        return item.get("value")

    def _get_health_ok(self, ctx: dict[str, Any]) -> Any:
        detection = self._bundle_value(ctx, "detection_results")
        if isinstance(detection, dict):
            health = detection.get("health_check", {})
            if isinstance(health, dict) and "ok" in health:
                return health.get("ok")
        return ctx.get("health_check", {}).get("ok")

    def _get_e2e_ok(self, ctx: dict[str, Any]) -> Any:
        detection = self._bundle_value(ctx, "detection_results")
        if isinstance(detection, dict):
            e2e = detection.get("e2e_memory_extract", {})
            if isinstance(e2e, dict) and "ok" in e2e:
                return e2e.get("ok")
        return ctx.get("e2e_memory_extract", {}).get("ok")

    def _get_uncommitted_count(self, ctx: dict[str, Any]) -> int:
        legacy_git = ctx.get("git_status", {})
        if isinstance(legacy_git, dict):
            count = legacy_git.get("uncommitted_count", 0)
            if isinstance(count, int):
                return count
        github = self._bundle_value(ctx, "github")
        if isinstance(github, dict):
            return 0
        return 0

    def _get_recent_errors(self, ctx: dict[str, Any]) -> list[str]:
        legacy = ctx.get("recent_errors", [])
        if isinstance(legacy, list) and legacy:
            return [str(x) for x in legacy]
        err = self._bundle_value(ctx, "error_library")
        if isinstance(err, dict):
            files = err.get("files", [])
            if isinstance(files, list):
                return [str(x) for x in files]
        return []

    def evaluate_rules(self, system_context: dict[str, Any]) -> list[dict[str, Any]]:
        """評估所有規則，回傳觸發的決策列表

        Args:
            system_context: 當前系統狀態 (health/e2e/git/error-log)

        Returns:
            觸發的決策列表 (按優先級排序)
        """
        triggered: list[dict[str, Any]] = []

        for rule in self.rules:
            try:
                if rule.condition(system_context):
                    triggered.append(
                        {
                            "id": rule.id,
                            "action": rule.action,
                            "priority": rule.priority,
                            "reason": rule.reason,
                            "auto_executable": rule.auto_executable,
                        }
                    )
            except Exception as e:
                print(f"⚠ 規則評估失敗 ({rule.id})：{e}")

        # 按優先級排序
        priority_map = {"P0": 0, "P1": 1, "P2": 2}
        triggered.sort(key=lambda d: priority_map.get(d["priority"], 3))

        return triggered

    def add_custom_rule(
        self,
        rule_id: str,
        condition: Callable[[dict[str, Any]], bool],
        action: str,
        priority: str,
        reason: str,
        auto_executable: bool = False,
    ) -> None:
        """動態加入自定義規則"""
        self.rules.append(
            Rule(
                id=rule_id,
                condition=condition,
                action=action,
                priority=priority,
                reason=reason,
                auto_executable=auto_executable,
            )
        )


def main() -> None:
    """測試決策規則引擎"""
    engine = DecisionRuleEngine()

    # 模擬系統狀態
    test_context = {
        "health_check": {"ok": False, "failed_at": "2026-03-18 14:00"},
        "e2e_memory_extract": {"ok": False, "failed_at": "2026-03-18 14:05"},
        "git_status": {"uncommitted_count": 2, "uncommitted_files": ["file1.py"]},
        "recent_errors": ["error.md"],
    }

    decisions = engine.evaluate_rules(test_context)

    print("\n" + "=" * 70)
    print("決策規則引擎評估結果")
    print("=" * 70)
    print(f"觸發 {len(decisions)} 個決策:")
    for i, decision in enumerate(decisions, 1):
        print(
            f"{i}. [{decision['priority']}] {decision['action']}"
            f" (auto={decision['auto_executable']})"
        )
        print(f"   原因：{decision['reason']}")

    print("\n✅ 決策規則引擎運行成功")


if __name__ == "__main__":
    main()

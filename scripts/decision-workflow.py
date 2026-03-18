#!/usr/bin/env python3
"""
decision-workflow.py — 決策確認 + 自動執行工作流

集成 decision-engine 的輸出，提供：
1. 人工確認界面（Y/N）
2. 自動執行決策對應的腳本
3. 結果回寫到 latest-handoff.md

典型工作流：
  decision-engine.py  → JSON 決策列表
  decision-workflow.py → 人工確認 → 自動執行 → 更新 handoff
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent.parent
LATEST_HANDOFF = BASE_DIR / "memory" / "handoff" / "latest-handoff.md"


class DecisionWorkflow:
    """決策工作流管理"""

    def __init__(self, decisions: list[dict[str, Any]]):
        self.decisions = decisions
        self.executed: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def confirm_and_execute(self, auto_mode: bool = False) -> dict[str, Any]:
        """執行工作流：確認 → 執行 → 記錄"""
        results = {
            "total": len(self.decisions),
            "executed": 0,
            "failed": 0,
            "skipped": 0,
            "timestamp": None,
        }

        for idx, decision in enumerate(self.decisions, 1):
            action = decision.get("action", "unknown")
            priority = decision.get("priority", "P?")
            auto = decision.get("auto_executable", False)

            # 確認邏輯
            should_execute = auto_mode or auto or self._prompt_confirm(idx, decision)

            if not should_execute:
                print(f"⊘ [{priority}] 跳過：{action}")
                results["skipped"] += 1
                continue

            # 執行邏輯
            success = self._execute_decision(decision)

            if success:
                self.executed.append(decision)
                results["executed"] += 1
                print(f"✅ [{priority}] 完成：{action}")
            else:
                self.failed.append(decision)
                results["failed"] += 1
                print(f"❌ [{priority}] 失敗：{action}")

        results["timestamp"] = self._now()
        return results

    def _prompt_confirm(self, idx: int, decision: dict[str, Any]) -> bool:
        """互動式確認"""
        action = decision.get("action", "unknown")
        reason = decision.get("reason", "")
        priority = decision.get("priority", "P?")

        print(f"\n[{idx}] {action} [{priority}]")
        print(f"    原因：{reason}")

        if not sys.stdin.isatty():
            # 非互動式環境，預設不執行
            return False

        response = input("    執行? (y/N): ").strip().lower()
        return response == "y"

    def _execute_decision(self, decision: dict[str, Any]) -> bool:
        """執行決策對應的腳本"""
        scripts = decision.get("scripts", [])
        if not scripts and decision.get("script"):
            scripts = [decision["script"]]

        for script in scripts:
            script_path = BASE_DIR / script
            if not script_path.exists():
                print(f"   ⚠ 腳本不存在：{script}")
                return False

            try:
                result = subprocess.run(
                    ["python3", str(script_path)],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode != 0:
                    print(f"   ❌ 腳本錯誤：{script}")
                    print(f"      {result.stderr[:200]}")
                    return False
            except Exception as e:
                print(f"   ❌ 執行失敗：{e}")
                return False

        return True

    def _now(self) -> str:
        """當前時間戳"""
        from datetime import datetime
        return datetime.now().isoformat()

    def update_handoff(self) -> None:
        """更新 latest-handoff.md"""
        if not LATEST_HANDOFF.exists():
            return

        # 簡單的文本替換（在實際應用中應使用更穩健的 markdown 解析）
        # TODO: 實現更完整的 handoff 更新邏輯


def main() -> None:
    """主程序"""
    # 模擬 decision-engine.py 的輸出
    # 在實際應用中應該由 decision-engine.py 的 JSON 提供

    sample_decisions = [
        {
            "id": "git_pending_changes",
            "priority": "P1",
            "action": "check_git_score_and_commit",
            "reason": "有 1 個未提交文件",
            "evidence": ["memory/status/swap-monitor.log"],
            "script": "scripts/git-score.py",
            "auto_executable": True,
        },
    ]

    workflow = DecisionWorkflow(sample_decisions)
    results = workflow.confirm_and_execute(auto_mode=True)

    print("\n" + "=" * 70)
    print("工作流執行結果")
    print("=" * 70)
    print(f"總計：{results['total']}")
    print(f"✅ 已執行：{results['executed']}")
    print(f"❌ 失敗：{results['failed']}")
    print(f"⊘ 跳過：{results['skipped']}")
    print(f"時間戳：{results['timestamp']}")


if __name__ == "__main__":
    main()

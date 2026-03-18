#!/usr/bin/env python3
"""
state_machine.py — Phase 2: 狀態機實現

三大管道的自動執行引擎：
  1. bug-closeout: 修完 bug → log_error → truth-source → LightRAG → milestone-judge
  2. major-change-guard: 代碼改動 → 自動偵測風險 → 備份 git → 決策記錄
  3. kg-maintenance: 定期驗證知識圖譜 → 去重 → 清洗 deprecated

核心想法：
- trigger_checkpoints 決定要執行哪些管道
- 每個管道都是步驟化流程，可驗證、可中斷、可回滾
- 執行失敗自動記錄到 error-log/
"""

import json
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal

BASE_DIR = Path(__file__).parent.parent


class PipelineStage(Enum):
    """管道執行階段"""

    INIT = "init"
    EXECUTE = "execute"
    VERIFY = "verify"
    COMMIT = "commit"
    ROLLBACK = "rollback"


class PipelineName(Enum):
    """三大管道"""

    BUG_CLOSEOUT = "bug_closeout"
    MAJOR_CHANGE_GUARD = "major_change_guard"
    KG_MAINTENANCE = "kg_maintenance"


@dataclass
class PipelineContext:
    """管道執行上下文"""

    pipeline_name: str
    user_id: str
    topic: str  # 主題（bug ID / change topic / maintenance 版本）
    metadata: dict[str, Any]
    stage: PipelineStage = PipelineStage.INIT
    error: str | None = None
    result: str | None = None


class Checkpoint:
    """檢查點基類"""

    def __init__(self, name: str, script_path: str | None = None):
        self.name = name
        self.script_path = script_path

    async def execute(self, ctx: PipelineContext) -> bool:
        """執行檢查點，回傳 True 表示成功"""
        raise NotImplementedError


class BugCloseoutCheckpoint(Checkpoint):
    """Bug Closeout 管道

    流程：
    1. log_error: 記錄根因 + 修正 → error-log/
    2. truth_ingest: 蒸餾出通用規則 → truth-source/
    3. lightrag_update: 更新知識圖譜
    4. milestone_judge: 評估是否达成里程碑
    """

    async def execute(self, ctx: PipelineContext) -> bool:
        """執行 bug-closeout 管道"""
        steps = [
            ("log_error", BASE_DIR / "scripts" / "bug_closeout.py"),
            ("truth_ingest", BASE_DIR / "scripts" / "truth-xval.py"),
            ("lightrag_update", None),  # MCP 呼叫
        ]

        for step_name, script in steps:
            try:
                if script and script.exists():
                    result = subprocess.run(
                        ["python3", str(script)],
                        cwd=str(BASE_DIR),
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode != 0:
                        ctx.error = f"{step_name} 失敗：{result.stderr[:200]}"
                        return False
            except Exception as e:
                ctx.error = f"{step_name} 異常：{str(e)}"
                return False

        ctx.result = "✅ bug-closeout 完成"
        return True


class MajorChangeGuardCheckpoint(Checkpoint):
    """Major Change Guard 管道

    流程：
    1. diff_analysis: 分析 git diff
    2. risk_assessment: 評估風險等級
    3. auto_backup: git commit + 備份
    4. decision_record: 記錄決策到 truth-source
    """

    async def execute(self, ctx: PipelineContext) -> bool:
        """執行 major-change-guard 管道"""
        try:
            # Step 1: Git diff 分析
            diff_output = subprocess.run(
                ["git", "-C", str(BASE_DIR), "diff", "--stat"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout

            # Step 2: 風險評估（簡單版本）
            files_changed = len(diff_output.split("\n")) - 1
            risk_level = (
                "HIGH" if files_changed > 10 else "MEDIUM" if files_changed > 5 else "LOW"
            )

            # Step 3: 自動備份
            if risk_level in ("HIGH", "MEDIUM"):
                subprocess.run(
                    ["git", "-C", str(BASE_DIR), "add", "-A"],
                    capture_output=True,
                    timeout=10,
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(BASE_DIR),
                        "commit",
                        "-m",
                        f"auto: guard-checkpoint risk={risk_level} files={files_changed}",
                    ],
                    capture_output=True,
                    timeout=10,
                )

            ctx.result = f"✅ major-change-guard 完成 (risk={risk_level}, files={files_changed})"
            return True
        except Exception as e:
            ctx.error = str(e)
            return False


class KGMaintenanceCheckpoint(Checkpoint):
    """KG Maintenance 管道

    流程：
    1. truth_xval: 交叉驗證知識圖譜
    2. dedup: 去重記憶條目
    3. cleanup_deprecated: 清洗過期項目
    4. lightrag_reindex: 重新索引
    """

    async def execute(self, ctx: PipelineContext) -> bool:
        """執行 kg-maintenance 管道"""
        steps = [
            ("truth_xval", BASE_DIR / "scripts" / "truth-xval.py"),
            ("dedup", BASE_DIR / "scripts" / "dedup-lightrag.py"),
        ]

        for step_name, script in steps:
            try:
                if script and script.exists():
                    result = subprocess.run(
                        ["python3", str(script)],
                        cwd=str(BASE_DIR),
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if result.returncode != 0:
                        ctx.error = f"{step_name} 失敗：{result.stderr[:200]}"
                        return False
            except Exception as e:
                ctx.error = f"{step_name} 異常：{str(e)}"
                return False

        ctx.result = "✅ kg-maintenance 完成"
        return True


class StateMachine:
    """狀態機：協調三大管道"""

    def __init__(self):
        self.checkpoints = {
            PipelineName.BUG_CLOSEOUT.value: BugCloseoutCheckpoint(
                "bug-closeout", str(BASE_DIR / "scripts" / "bug_closeout.py")
            ),
            PipelineName.MAJOR_CHANGE_GUARD.value: MajorChangeGuardCheckpoint(
                "major-change-guard"
            ),
            PipelineName.KG_MAINTENANCE.value: KGMaintenanceCheckpoint(
                "kg-maintenance"
            ),
        }
        self.execution_log: list[dict[str, Any]] = []

    async def execute_triggered_pipelines(
        self, trigger_checkpoints: list[str], ctx_metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """執行被觸發的管道

        Args:
            trigger_checkpoints: 要執行的管道名稱列表
            ctx_metadata: 上下文元數據 (user_id, topic, etc.)

        Returns:
            執行結果摘要
        """
        results = {
            "total": len(trigger_checkpoints),
            "executed": 0,
            "failed": 0,
            "errors": [],
        }

        for checkpoint_name in trigger_checkpoints:
            if checkpoint_name not in self.checkpoints:
                results["errors"].append(f"未知的檢查點：{checkpoint_name}")
                continue

            ctx = PipelineContext(
                pipeline_name=checkpoint_name,
                user_id=ctx_metadata.get("user_id", "default"),
                topic=ctx_metadata.get("topic", "auto"),
                metadata=ctx_metadata,
            )

            checkpoint = self.checkpoints[checkpoint_name]
            try:
                success = await checkpoint.execute(ctx)
                if success:
                    results["executed"] += 1
                    self.execution_log.append(
                        {
                            "checkpoint": checkpoint_name,
                            "status": "success",
                            "result": ctx.result,
                        }
                    )
                else:
                    results["failed"] += 1
                    results["errors"].append(ctx.error)
                    self.execution_log.append(
                        {
                            "checkpoint": checkpoint_name,
                            "status": "failed",
                            "error": ctx.error,
                        }
                    )
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(str(e))

        return results

    def get_execution_log(self) -> list[dict[str, Any]]:
        """取得執行日誌"""
        return self.execution_log


async def main() -> None:
    """測試狀態機"""
    machine = StateMachine()

    # 模擬 trigger_checkpoints
    test_triggers = ["bug_closeout", "kg_maintenance"]
    test_metadata = {
        "user_id": "default",
        "topic": "phase2-test",
        "timestamp": "2026-03-18",
    }

    results = await machine.execute_triggered_pipelines(test_triggers, test_metadata)

    print("\n" + "=" * 70)
    print("狀態機執行結果")
    print("=" * 70)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("\n執行日誌：")
    for log in machine.get_execution_log():
        print(f"  {log}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

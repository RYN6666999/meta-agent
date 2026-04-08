#!/usr/bin/env python3
"""
guard.py — 靜態自檢（不需啟動 server）
對標 vibe-coding-template guard:all

檢查項目：
  G1  schema JSON 可解析 + 必要欄位存在
  G2  MvpSceneCard 欄位完整（model_used / prompt_version）
  G3  Mock LLM 端到端 pipeline 可跑通
  G4  from_mvp_card / to_mvp 欄位傳遞正確
  G5  Pydantic 驗證：缺少必要欄位時正確拒絕

用法：
  python3 scripts/guard.py
  python3 scripts/guard.py --only G1 G3
"""
import sys
import json
import asyncio
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PASS = "\033[32m PASS\033[0m"
FAIL = "\033[31m FAIL\033[0m"

results: list[bool] = []


def check(label: str, cond: bool, detail: str = "") -> bool:
    status = PASS if cond else FAIL
    print(f"  {status}  {label}" + (f"  [{detail}]" if detail else ""))
    results.append(cond)
    return cond


# ─────────────────────────────────────────────────────────
# G1: JSON Schema 完整性
# ─────────────────────────────────────────────────────────
def test_g1():
    print("\n[G1] framework_card.json schema 完整性")
    schema_path = ROOT / "schemas" / "framework_card.json"

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as e:
        check("schema 可解析", False, str(e))
        return

    props = schema.get("properties", {})
    required = schema.get("required", [])

    for field in ("summary", "characters", "situation", "mind", "desire",
                  "change", "change_intensity", "quotes"):
        check(f"required 含 {field}", field in required)

    check("properties 含 model_used",   "model_used"   in props)
    check("properties 含 prompt_version", "prompt_version" in props)

    deferred = schema.get("_deferred", {}).get("deferred_fields", [])
    check("model_used 已從 _deferred 移除",   "model_used"   not in deferred)
    check("prompt_version 已從 _deferred 移除", "prompt_version" not in deferred)


# ─────────────────────────────────────────────────────────
# G2: MvpSceneCard 欄位完整
# ─────────────────────────────────────────────────────────
def test_g2():
    print("\n[G2] MvpSceneCard 欄位完整性")
    try:
        from backend.app.models.scene_framework_card import MvpSceneCard
    except Exception as e:
        check("MvpSceneCard import", False, str(e))
        return

    fields = MvpSceneCard.model_fields
    check("MvpSceneCard 有 model_used",    "model_used"    in fields)
    check("MvpSceneCard 有 prompt_version", "prompt_version" in fields)

    # 預設值不可為 None
    card = MvpSceneCard(
        book_id="b", chapter_index=1, scene_index=1,
        summary="s", characters=["A"],
        situation="局", mind="心", desire="欲", change="變",
        change_intensity=3, quotes=["q"],
    )
    check("model_used 預設為字串", isinstance(card.model_used, str))
    check("prompt_version 預設為字串", isinstance(card.prompt_version, str))


# ─────────────────────────────────────────────────────────
# G3: Mock LLM 端到端 pipeline
# ─────────────────────────────────────────────────────────
def test_g3():
    print("\n[G3] Mock LLM 端到端 pipeline")
    try:
        from backend.app.services.framework_analyzer import (
            MockLLMClient, FrameworkAnalyzer, AnalysisContext,
        )
    except Exception as e:
        check("analyzer import", False, str(e))
        return

    async def run():
        analyzer = FrameworkAnalyzer(llm_client=MockLLMClient())
        ctx = AnalysisContext(
            scene_id="g3_test", book_id="test",
            scene_text="寧凡說：「你沒有別的選擇。」",
            chapter_number=1, scene_number=1,
            focal_character="寧凡",
        )
        return await analyzer.analyze(ctx)

    try:
        result = asyncio.run(run())
        check("pipeline 執行不拋錯", True)
        check("card.model_used 非空", bool(result.card.model_used),
              result.card.model_used)
        check("card.prompt_version 非空", bool(result.card.prompt_version),
              result.card.prompt_version)
        check("card.quotes 至少一條", len(result.card.quotes) >= 1)
        check("card.situation 非空", bool(result.card.situation))
    except Exception as e:
        check("pipeline 執行不拋錯", False, str(e))


# ─────────────────────────────────────────────────────────
# G4: from_mvp_card / to_mvp 欄位傳遞
# ─────────────────────────────────────────────────────────
def test_g4():
    print("\n[G4] from_mvp_card / to_mvp 欄位傳遞")
    try:
        from backend.app.models.scene_framework_card import MvpSceneCard, SceneFrameworkCard
    except Exception as e:
        check("models import", False, str(e))
        return

    card = MvpSceneCard(
        book_id="b", chapter_index=1, scene_index=1,
        summary="s", characters=["寧凡"],
        situation="局", mind="心", desire="欲", change="變",
        change_intensity=3, quotes=["原文"],
        model_used="claude-haiku-4-5-20251001",
        prompt_version="mvp-1",
    )
    orm = SceneFrameworkCard.from_mvp_card(card, raw_text="原文")
    check("ORM.model_used 正確寫入",    orm.model_used    == "claude-haiku-4-5-20251001")
    check("ORM.prompt_version 正確寫入", orm.prompt_version == "mvp-1")

    d = orm.to_mvp()
    check("to_mvp 含 model_used",    "model_used"    in d)
    check("to_mvp 含 prompt_version", "prompt_version" in d)
    check("to_mvp model_used 值正確", d["model_used"] == "claude-haiku-4-5-20251001")


# ─────────────────────────────────────────────────────────
# G5: Pydantic 拒絕不合法輸入
# ─────────────────────────────────────────────────────────
def test_g5():
    print("\n[G5] Pydantic 驗證：缺欄位時正確拒絕")
    try:
        from pydantic import ValidationError
        from backend.app.models.scene_framework_card import MvpSceneCard
    except Exception as e:
        check("import", False, str(e))
        return

    try:
        MvpSceneCard(book_id="b", chapter_index=1, scene_index=1)
        check("缺少必要欄位時應拋 ValidationError", False, "沒有拋錯")
    except Exception as e:
        check("缺少必要欄位時正確拋 ValidationError", "ValidationError" in type(e).__name__,
              type(e).__name__)

    try:
        MvpSceneCard(
            book_id="b", chapter_index=1, scene_index=1,
            summary="s", characters=["A"],
            situation="局", mind="心", desire="欲", change="變",
            change_intensity=9,  # 超出 1-5 範圍
            quotes=["q"],
        )
        check("change_intensity=9 應被拒絕", False, "沒有拋錯")
    except Exception:
        check("change_intensity 超範圍時正確拒絕", True)


# ─────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────
TESTS = {
    "G1": ("schema 完整性",           test_g1),
    "G2": ("MvpSceneCard 欄位",       test_g2),
    "G3": ("Mock LLM pipeline",      test_g3),
    "G4": ("from_mvp_card/to_mvp",   test_g4),
    "G5": ("Pydantic 驗證",           test_g5),
}


def main():
    parser = argparse.ArgumentParser(description="Novel Analyzer Static Guard")
    parser.add_argument("--only", nargs="*", help="只跑指定 id，例如 G1 G3")
    args = parser.parse_args()

    run_ids = args.only if args.only else list(TESTS.keys())

    for tid in run_ids:
        if tid not in TESTS:
            print(f"[SKIP] 未知 id: {tid}")
            continue
        TESTS[tid][1]()

    passed = sum(results)
    total  = len(results)
    failed = total - passed

    print("\n" + "─" * 48)
    print(f"結果  通過 {passed}/{total}")
    if failed:
        print(f"未通過 {failed} 項 ← 修完再 commit")
        sys.exit(1)
    else:
        print("全部通過 ✓")


if __name__ == "__main__":
    main()

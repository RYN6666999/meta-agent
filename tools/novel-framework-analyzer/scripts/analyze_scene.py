"""
analyze_scene.py
================
端對端測試：取第 1 章第 1 個場景，用 Ollama 做框架分析，印出結果。

執行（模型下載完成後）：
    python3 scripts/analyze_scene.py
    python3 scripts/analyze_scene.py --chapter 3 --scene 2
    python3 scripts/analyze_scene.py --mock   ← 不需要 Ollama，用 mock 測試
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.services.scene_splitter import split_chapters, split_scenes
from backend.app.services.framework_analyzer import FrameworkAnalyzer, MockLLMClient, AnalysisContext

NOVEL_PATH = os.path.join(ROOT, "上城之下.txt")
BOOK_ID = "shangchengzhixia-001"


async def main(chapter_num: int, scene_num: int, use_mock: bool):
    # 1. 讀小說
    with open(NOVEL_PATH, encoding="utf-8") as f:
        text = f.read()

    # 2. 切章取目標章節
    chapters = split_chapters(text, BOOK_ID)
    chapter = next((c for c in chapters if c.chapter_number == chapter_num), None)
    if not chapter:
        print(f"找不到第 {chapter_num} 章")
        return

    # 3. 切場景取目標場景
    scenes = split_scenes(chapter)
    scene = next((s for s in scenes if s.scene_number == scene_num), None)
    if not scene:
        print(f"第 {chapter_num} 章沒有第 {scene_num} 個場景（共 {len(scenes)} 個）")
        return

    print(f"=== 第 {chapter_num} 章「{chapter.title}」· 場景 {scene_num} ===")
    print(f"字數：{scene.char_count}，切分原因：{scene.boundary_reason}")
    print(f"\n【場景原文前 200 字】\n{scene.raw_text[:200]}...\n")
    print("=" * 60)

    # 4. 選 LLM
    if use_mock:
        print("[使用 Mock LLM，不呼叫真實模型]")
        llm = MockLLMClient()
    else:
        # 載入 .env
        env_path = os.path.join(ROOT, ".env")
        api_key = None
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("OPENROUTER_API_KEY="):
                    api_key = line.strip().split("=", 1)[1]
        if not api_key:
            print("找不到 OPENROUTER_API_KEY，請在 .env 中設定")
            return
        # 優先用 Ollama（免費），沒有再用 OpenRouter
        from services.llm.ollama_adapter import OllamaClient
        ollama = OllamaClient(model="qwen2.5:7b")
        if await ollama.health_check():
            models = await ollama.list_models()
            if any("qwen2.5:7b" in m for m in models):
                llm = ollama
                print("[使用 Ollama qwen2.5:7b（本地免費）]")
            else:
                print(f"qwen2.5:7b 尚未下載完成，目前已有：{models}")
                print("改用 OpenRouter...")
                from services.llm.openrouter_adapter import OpenRouterClient
                llm = OpenRouterClient(api_key=api_key, model="anthropic/claude-haiku-4-5")
                print(f"[使用 OpenRouter — {llm.model_id}]")
        else:
            print("Ollama 未啟動，改用 OpenRouter...")
            from services.llm.openrouter_adapter import OpenRouterClient
            llm = OpenRouterClient(api_key=api_key, model="anthropic/claude-haiku-4-5")
            print(f"[使用 OpenRouter — {llm.model_id}]")

    # 5. 建分析器
    analyzer = FrameworkAnalyzer(
        llm_client=llm,
        prompt_dir=os.path.join(ROOT, "prompts"),
    )

    # 6. 分析
    ctx = AnalysisContext(
        scene_id=scene.scene_id,
        book_id=BOOK_ID,
        scene_text=scene.raw_text,
        chapter_number=chapter_num,
        scene_number=scene_num,
        focal_character="寧凡",  # 主角
    )

    print("分析中...")
    try:
        result = await analyzer.analyze(ctx)
        card = result.card
    except Exception as e:
        print(f"分析失敗：{e}")
        return

    # 7. 印出結果
    print(f"\n✅ 分析完成（retry={result.retry_count}, tokens={result.total_tokens}）\n")

    print("【局 — 外部局勢】")
    print(f"  局勢：{card.situation.external_situation}")
    print(f"  權力：{card.situation.power_dynamics}")
    print(f"  主動方：{card.situation.active_party}")
    for q in card.situation.evidence_quotes[:1]:
        print(f"  📖 原文：「{q.text[:60]}」")

    print("\n【欲 — 角色欲望】")
    print(f"  顯性：{card.desire.explicit_desire}")
    print(f"  隱性：{card.desire.implicit_desire}")
    for q in card.desire.evidence_quotes[:1]:
        print(f"  📖 原文：「{q.text[:60]}」")

    print("\n【心變 — 心態轉變】")
    print(f"  前：{card.mind_shift.before_mindset}")
    print(f"  觸發：{card.mind_shift.trigger_event}")
    print(f"  後：{card.mind_shift.after_mindset}")
    print(f"  類型：{card.mind_shift.shift_type}")
    for q in card.mind_shift.evidence_quotes[:1]:
        print(f"  📖 原文：「{q.text[:60]}」")

    print("\n【框架判定】")
    print(f"  符合等級：{card.judgment.match_level}")
    print(f"  信心分數：{card.judgment.confidence_score:.2f}")
    print(f"  理由：{card.judgment.reasoning[:100]}")

    # 儲存完整 JSON
    out_path = os.path.join(ROOT, f"output_ch{chapter_num}_s{scene_num}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(card.model_dump_json(indent=2))
    print(f"\n💾 完整 JSON 已存至：{out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", type=int, default=1)
    parser.add_argument("--scene", type=int, default=1)
    parser.add_argument("--mock", action="store_true", help="用 Mock LLM 測試")
    args = parser.parse_args()
    asyncio.run(main(args.chapter, args.scene, args.mock))

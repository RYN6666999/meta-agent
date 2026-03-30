"""
quality_compare.py
==================
比較不同 LLM 對同一場景的分析品質。
Qwen2.5:7b（本地）vs Claude Haiku（OpenRouter）

執行：
    python3 scripts/quality_compare.py                    # 比較第1章前3場景
    python3 scripts/quality_compare.py --chapter 3        # 比較特定章節
    python3 scripts/quality_compare.py --scenes 5         # 比較前N個場景
    python3 scripts/quality_compare.py --models haiku     # 只跑一個模型（快速測試）
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.services.scene_splitter import split_chapters, split_scenes
from backend.app.services.character_extractor import extract_characters
from backend.app.services.framework_analyzer import FrameworkAnalyzer, AnalysisContext, AnalysisError

NOVEL_PATH = os.path.join(ROOT, "上城之下.txt")
BOOK_ID    = "shangchengzhixia-001"


def build_clients(models_str: str, env_path: str):
    """建立要比較的 LLM clients"""
    api_key = None
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("OPENROUTER_API_KEY="):
                api_key = line.strip().split("=", 1)[1]

    clients = {}

    if "ollama" in models_str or models_str == "all":
        import httpx
        try:
            resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
            if resp.status_code == 200:
                available = [m["name"] for m in resp.json().get("models", [])]
                if any("qwen2.5:7b" in m for m in available):
                    from services.llm.ollama_adapter import OllamaClient
                    clients["qwen2.5:7b"] = OllamaClient(model="qwen2.5:7b")
                    print("✅ Ollama qwen2.5:7b 可用")
                else:
                    print(f"⚠️  qwen2.5:7b 未下載完成（現有：{available}）")
        except Exception:
            print("⚠️  Ollama 未啟動，跳過")

    if ("haiku" in models_str or models_str == "all") and api_key:
        from services.llm.openrouter_adapter import OpenRouterClient
        clients["claude-haiku"] = OpenRouterClient(
            api_key=api_key, model="anthropic/claude-haiku-4-5"
        )
        print("✅ Claude Haiku (OpenRouter) 可用")

    return clients


def score_card(card) -> dict:
    """對分析卡打分，用於量化比較"""
    scores = {}

    # 1. Evidence 品質：引用句平均長度（太短=可能假引用）
    all_quotes = []
    for dim in ("situation", "desire", "mind_shift"):
        dim_obj = getattr(card, dim)
        all_quotes.extend(dim_obj.evidence_quotes)
    if card.judgment.key_evidence_quotes:
        all_quotes.extend(card.judgment.key_evidence_quotes)

    avg_quote_len = sum(len(q.text) for q in all_quotes) / max(len(all_quotes), 1)
    scores["avg_quote_len"] = round(avg_quote_len, 1)

    # 2. 分析深度：各維度文字長度
    scores["situation_depth"] = len(card.situation.external_situation)
    scores["desire_depth"] = len(card.desire.implicit_desire)
    scores["mindshift_depth"] = len(card.mind_shift.shift_description)

    # 3. 信心分數
    scores["confidence"] = card.judgment.confidence_score

    # 4. 符合等級
    level_map = {"full": 4, "partial": 3, "weak": 2, "none": 1}
    level_str = card.judgment.match_level
    if hasattr(level_str, "value"):
        level_str = level_str.value
    scores["match_score"] = level_map.get(level_str, 0)
    scores["match_level"] = level_str

    # 5. 引用是否像原文（含漢字比例 > 80%）
    cjk_ratio = []
    for q in all_quotes:
        cjk = sum(1 for c in q.text if "\u4e00" <= c <= "\u9fff")
        cjk_ratio.append(cjk / max(len(q.text), 1))
    scores["quote_cjk_ratio"] = round(sum(cjk_ratio) / max(len(cjk_ratio), 1), 2)

    # 綜合分（0-100）
    scores["total"] = round(
        min(avg_quote_len / 30, 1) * 25 +     # 引用長度
        scores["confidence"] * 25 +             # 信心
        scores["match_score"] / 4 * 25 +        # 符合等級
        scores["quote_cjk_ratio"] * 25,         # 引用純度
        1
    )

    return scores


def print_comparison(scene_label: str, results: dict):
    """並排印出各模型的分析結果比較"""
    print(f"\n{'='*70}")
    print(f"場景：{scene_label}")
    print(f"{'='*70}")

    headers = list(results.keys())
    if not headers:
        print("  無結果")
        return

    # 表頭
    print(f"{'指標':<20}", end="")
    for model in headers:
        print(f"  {model:<20}", end="")
    print()
    print("-" * (20 + 22 * len(headers)))

    # 取得所有分數
    scores_by_model = {}
    for model, (card, elapsed) in results.items():
        if card:
            scores_by_model[model] = score_card(card)
            scores_by_model[model]["elapsed"] = round(elapsed, 1)
        else:
            scores_by_model[model] = {}

    metrics = [
        ("match_level",      "符合等級"),
        ("confidence",       "信心分數"),
        ("avg_quote_len",    "引用平均字數"),
        ("quote_cjk_ratio",  "引用純度"),
        ("situation_depth",  "局分析深度"),
        ("desire_depth",     "欲分析深度"),
        ("mindshift_depth",  "心變分析深度"),
        ("total",            "綜合分(0-100)"),
        ("elapsed",          "耗時(秒)"),
    ]

    for key, label in metrics:
        print(f"  {label:<18}", end="")
        for model in headers:
            val = scores_by_model.get(model, {}).get(key, "N/A")
            print(f"  {str(val):<20}", end="")
        print()

    # 印出關鍵引用對比
    print(f"\n{'─'*70}")
    print("關鍵原文引用對比：")
    for model, (card, _) in results.items():
        if not card:
            continue
        quotes = card.judgment.key_evidence_quotes
        if quotes:
            q = quotes[0].text[:60]
            print(f"  [{model:15s}] {q}{'...' if len(quotes[0].text) > 60 else ''}")


async def analyze_scene_with_model(analyzer, ctx) -> tuple:
    """跑一個場景，返回 (card, elapsed)"""
    t0 = time.time()
    try:
        result = await analyzer.analyze(ctx)
        return result.card, time.time() - t0
    except AnalysisError as e:
        print(f"    ❌ 分析失敗：{e}")
        return None, time.time() - t0


async def main(chapter_num: int, n_scenes: int, models_str: str):
    env_path = os.path.join(ROOT, ".env")
    clients = build_clients(models_str, env_path)

    if not clients:
        print("沒有可用的 LLM，請確認 Ollama 已下載或 .env 有 OPENROUTER_API_KEY")
        return

    # 建分析器：Ollama 用 MSA（省 token，適合 8GB RAM）；OpenRouter 用完整版
    from backend.app.services.msa_analyzer import MSAAnalyzer
    analyzers = {}
    for name, client in clients.items():
        if "qwen" in name or "ollama" in name.lower():
            analyzers[name] = MSAAnalyzer(llm_client=client)
            print(f"  [{name}] → MSA 模式（省 token）")
        else:
            analyzers[name] = FrameworkAnalyzer(
                llm_client=client,
                prompt_dir=os.path.join(ROOT, "prompts"),
            )
            print(f"  [{name}] → 完整分析模式")

    # 讀小說，切場景
    with open(NOVEL_PATH, encoding="utf-8") as f:
        text = f.read()

    chapters = split_chapters(text, BOOK_ID)
    chapter = next((c for c in chapters if c.chapter_number == chapter_num), None)
    if not chapter:
        print(f"找不到第 {chapter_num} 章")
        return

    scenes = split_scenes(chapter)[:n_scenes]
    print(f"\n比較對象：第 {chapter_num} 章「{chapter.title}」前 {len(scenes)} 個場景")
    print(f"模型：{list(clients.keys())}\n")

    total_scores = {name: [] for name in clients}

    for scene in scenes:
        focal, secondary = extract_characters(scene.raw_text)
        ctx = AnalysisContext(
            scene_id=scene.scene_id,
            book_id=BOOK_ID,
            scene_text=scene.raw_text,
            chapter_number=chapter_num,
            scene_number=scene.scene_number,
            focal_character=focal,
            known_characters=secondary,
        )

        # 逐模型分析（不並發，確保公平計時）
        results = {}
        for name, analyzer in analyzers.items():
            print(f"  [{name}] 分析場景 {scene.scene_number}...", end="", flush=True)
            card, elapsed = await analyze_scene_with_model(analyzer, ctx)
            print(f" {elapsed:.1f}s")
            results[name] = (card, elapsed)
            if card:
                total_scores[name].append(score_card(card)["total"])

        print_comparison(
            f"ch{chapter_num} s{scene.scene_number} | {scene.char_count}字 | 主角:{focal}",
            results,
        )

    # 總結
    print(f"\n{'='*70}")
    print("總結（各模型平均分）")
    for name, scores in total_scores.items():
        avg = sum(scores) / len(scores) if scores else 0
        print(f"  {name:<20} 平均分：{avg:.1f}  （{len(scores)} 場景）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="比較不同 LLM 的分析品質")
    parser.add_argument("--chapter", type=int, default=1)
    parser.add_argument("--scenes", type=int, default=3, help="比較前N個場景")
    parser.add_argument("--models", default="all",
                        choices=["all", "ollama", "haiku"],
                        help="要比較的模型")
    args = parser.parse_args()
    asyncio.run(main(args.chapter, args.scenes, args.models))

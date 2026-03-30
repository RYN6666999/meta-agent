"""
batch_analyze.py
================
批次分析腳本：讀取指定章節範圍，切場景，自動偵測角色，LLM 分析，存 SQLite。

執行：
    python3 scripts/batch_analyze.py --chapters 1-5
    python3 scripts/batch_analyze.py --chapters 1-10 --model sonnet   # 高品質
    python3 scripts/batch_analyze.py --chapters 1-5 --skip-existing   # 跳過已分析
    python3 scripts/batch_analyze.py --chapters 1-5 --dry-run         # 只切場景不分析
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.database import init_db, SessionLocal
from backend.app.models.scene_framework_card import SceneFrameworkCard
from backend.app.services.scene_splitter import split_chapters, split_scenes
from backend.app.services.character_extractor import extract_characters
from backend.app.services.framework_analyzer import (
    FrameworkAnalyzer, AnalysisContext, AnalysisError, MockLLMClient
)

NOVEL_PATH = os.path.join(ROOT, "上城之下.txt")
BOOK_ID    = "shangchengzhixia-001"


# ---------------------------------------------------------------------------
# LLM 工廠
# ---------------------------------------------------------------------------

def build_llm(model_choice: str, env_path: str):
    """依設定選擇 LLM：ollama > openrouter > mock"""
    api_key = None
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("OPENROUTER_API_KEY="):
                api_key = line.strip().split("=", 1)[1]

    if model_choice == "mock":
        print("[LLM] Mock 模式")
        return MockLLMClient()

    # 嘗試 Ollama
    import httpx
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            target = "qwen2.5:7b"
            if model_choice == "sonnet":
                target = None  # 強制走 OpenRouter
            if target and any(target in m for m in models):
                from services.llm.ollama_adapter import OllamaClient
                print(f"[LLM] Ollama {target}（本地免費）")
                return OllamaClient(model=target)
    except Exception:
        pass

    # Fallback: OpenRouter
    if not api_key:
        print("[LLM] 找不到 API key，使用 Mock")
        return MockLLMClient()

    from services.llm.openrouter_adapter import OpenRouterClient
    model_map = {
        "haiku":  "anthropic/claude-haiku-4-5",
        "sonnet": "anthropic/claude-sonnet-4-5",
        "gemini": "google/gemini-flash-1.5",
    }
    or_model = model_map.get(model_choice, "anthropic/claude-haiku-4-5")
    print(f"[LLM] OpenRouter {or_model}")
    return OpenRouterClient(api_key=api_key, model=or_model)


# ---------------------------------------------------------------------------
# 統計收集
# ---------------------------------------------------------------------------

@dataclass
class RunStats:
    chapters: int = 0
    scenes_total: int = 0
    scenes_analyzed: int = 0
    scenes_skipped: int = 0
    scenes_failed: int = 0
    tokens_used: int = 0
    elapsed: float = 0.0
    match_counts: dict = field(default_factory=lambda: {
        "full": 0, "partial": 0, "weak": 0, "none": 0
    })

    def print_summary(self):
        print("\n" + "=" * 60)
        print("批次分析完成")
        print(f"  章節：{self.chapters} 章")
        print(f"  場景：{self.scenes_total} 個")
        print(f"    ✅ 成功：{self.scenes_analyzed}")
        print(f"    ⏭  跳過：{self.scenes_skipped}")
        print(f"    ❌ 失敗：{self.scenes_failed}")
        print(f"  框架符合分布：", end="")
        for level, count in self.match_counts.items():
            if count:
                pct = count / max(self.scenes_analyzed, 1) * 100
                print(f"{level}={count}({pct:.0f}%) ", end="")
        print()
        if self.tokens_used:
            print(f"  Token 用量：{self.tokens_used:,}")
        print(f"  耗時：{self.elapsed:.1f} 秒")
        if self.scenes_analyzed:
            print(f"  平均每場景：{self.elapsed / self.scenes_analyzed:.1f} 秒")
        print("=" * 60)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run(
    chapter_start: int,
    chapter_end: int,
    model_choice: str,
    skip_existing: bool,
    dry_run: bool,
    concurrency: int,
    use_msa: bool = False,
):
    # 初始化 DB
    init_db()
    db = SessionLocal()
    stats = RunStats()
    t0 = time.time()

    # 讀小說
    with open(NOVEL_PATH, encoding="utf-8") as f:
        text = f.read()

    # 建 LLM + 分析器
    env_path = os.path.join(ROOT, ".env")
    llm = build_llm(model_choice, env_path)
    if use_msa:
        from backend.app.services.msa_analyzer import MSAAnalyzer
        analyzer = MSAAnalyzer(llm_client=llm)
        print("[模式] Multi-Stage Analysis（省 ~45% tokens）")
    else:
        analyzer = FrameworkAnalyzer(
            llm_client=llm,
            prompt_dir=os.path.join(ROOT, "prompts"),
        )

    # 取已存在的 scene_id（用於 skip）
    existing_scene_ids: set[str] = set()
    if skip_existing:
        rows = db.query(SceneFrameworkCard.scene_id).all()
        existing_scene_ids = {r[0] for r in rows}
        print(f"DB 中已有 {len(existing_scene_ids)} 個場景卡，跳過重複分析")

    # 切章節
    chapters = [
        c for c in split_chapters(text, BOOK_ID)
        if chapter_start <= c.chapter_number <= chapter_end
    ]
    stats.chapters = len(chapters)
    print(f"\n開始分析：第 {chapter_start}–{chapter_end} 章（共 {len(chapters)} 章）")

    # 建立 semaphore 控制並發
    sem = asyncio.Semaphore(concurrency)

    async def analyze_one(chapter, scene) -> Optional[SceneFrameworkCard]:
        async with sem:
            if scene.scene_id in existing_scene_ids:
                stats.scenes_skipped += 1
                return None

            if dry_run:
                focal, secondary = extract_characters(scene.raw_text)
                print(f"  [DRY] ch{chapter.chapter_number} s{scene.scene_number} "
                      f"| {scene.char_count}字 | 主角:{focal}")
                stats.scenes_analyzed += 1
                return None

            focal, secondary = extract_characters(scene.raw_text)

            ctx = AnalysisContext(
                scene_id=scene.scene_id,
                book_id=BOOK_ID,
                scene_text=scene.raw_text,
                chapter_number=chapter.chapter_number,
                scene_number=scene.scene_number,
                focal_character=focal,
                known_characters=secondary,
            )

            try:
                result = await analyzer.analyze(ctx)
                card = result.card
                stats.tokens_used += result.total_tokens

                # 存 DB
                orm = SceneFrameworkCard.from_schema(card, scene_text=scene.raw_text)
                db.add(orm)
                db.commit()

                level = card.judgment.match_level
                level_str = level.value if hasattr(level, "value") else level
                stats.match_counts[level_str] = stats.match_counts.get(level_str, 0) + 1
                stats.scenes_analyzed += 1

                conf = card.judgment.confidence_score
                conf_icon = "🟢" if conf >= 0.8 else "🟡" if conf >= 0.5 else "🔴"
                print(f"  {conf_icon} ch{chapter.chapter_number:3d} s{scene.scene_number} "
                      f"| {level_str:7s} | conf={conf:.2f} | 主角:{focal[:4]:4s} "
                      f"| retry={result.retry_count}")
                return orm

            except AnalysisError as e:
                stats.scenes_failed += 1
                print(f"  ❌ ch{chapter.chapter_number} s{scene.scene_number} 失敗：{e}")
                db.rollback()
                return None

    # 逐章處理（章內場景可並發）
    for chapter in chapters:
        scenes = split_scenes(chapter)
        stats.scenes_total += len(scenes)
        print(f"\n【第 {chapter.chapter_number} 章】{chapter.title} — {len(scenes)} 個場景")

        tasks = [analyze_one(chapter, scene) for scene in scenes]
        await asyncio.gather(*tasks)

    db.close()
    stats.elapsed = time.time() - t0
    stats.print_summary()


def main():
    parser = argparse.ArgumentParser(description="批次分析《上城之下》")
    parser.add_argument("--chapters", default="1-5",
                        help="章節範圍，如 1-5 或 10-20")
    parser.add_argument("--model",    default="auto",
                        choices=["auto", "mock", "haiku", "sonnet", "gemini"],
                        help="LLM 選擇（auto=優先Ollama）")
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳過 DB 中已存在的場景")
    parser.add_argument("--dry-run", action="store_true",
                        help="只切場景 + 角色偵測，不呼叫 LLM")
    parser.add_argument("--concurrency", type=int, default=2,
                        help="同時分析的場景數（Ollama 建議1-2，OpenRouter可3-5）")
    parser.add_argument("--msa", action="store_true",
                        help="使用多階段分析，省約45%% tokens")
    args = parser.parse_args()

    parts = args.chapters.split("-")
    start = int(parts[0])
    end   = int(parts[1]) if len(parts) > 1 else start

    asyncio.run(run(
        chapter_start=start,
        chapter_end=end,
        model_choice=args.model,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
        use_msa=args.msa,
    ))


if __name__ == "__main__":
    main()

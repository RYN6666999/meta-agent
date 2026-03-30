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

FREE_MODELS = {
    # OpenRouter 免費模型（rate limit 存在，但無費用）
    # 中文友好排序：GLM > Llama70B > Qwen3 > Gemma27B
    "free-glm":    "z-ai/glm-4.5-air:free",               # 中文專屬，最推薦
    "free-llama":  "meta-llama/llama-3.3-70b-instruct:free",  # 70B，中文可用
    "free-qwen":   "qwen/qwen3-coder:free",               # Qwen3，中文強
    "free-gemma":  "google/gemma-3-27b-it:free",          # 27B Gemma
    "free-gpt":    "openai/gpt-oss-120b:free",            # 120B GPT OSS
}


def _load_api_key(env_path: str) -> Optional[str]:
    if not os.path.exists(env_path):
        return None
    for line in open(env_path):
        if line.startswith("OPENROUTER_API_KEY="):
            return line.strip().split("=", 1)[1]
    return None


def _load_gemini_key(env_path: str) -> Optional[str]:
    if not os.path.exists(env_path):
        return None
    for line in open(env_path):
        if line.startswith("GEMINI_API_KEY="):
            return line.strip().split("=", 1)[1]
    return None


def _ollama_available() -> bool:
    import httpx
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            return any("qwen2.5:7b" in m for m in models)
    except Exception:
        pass
    return False


def build_llm(model_choice: str, env_path: str):
    """依設定選擇 LLM（單一分析器模式）"""
    api_key = _load_api_key(env_path)

    if model_choice == "mock":
        print("[LLM] Mock 模式")
        return MockLLMClient()

    if model_choice == "local":
        if _ollama_available():
            from services.llm.ollama_adapter import OllamaClient
            print("[LLM] Ollama qwen2.5:7b（本地，慢但免費）")
            return OllamaClient(model="qwen2.5:7b")
        print("[LLM] Ollama 不可用，fallback → Haiku")
        model_choice = "haiku"

    if not api_key:
        print("[LLM] 找不到 API key，使用 Mock")
        return MockLLMClient()

    from services.llm.openrouter_adapter import OpenRouterClient

    # 免費模型
    if model_choice in FREE_MODELS:
        m = FREE_MODELS[model_choice]
        print(f"[LLM] OpenRouter 免費模型：{m}")
        return OpenRouterClient(api_key=api_key, model=m)

    model_map = {
        "haiku":  "anthropic/claude-haiku-4-5",
        "sonnet": "anthropic/claude-sonnet-4-5",
        "gemini": "google/gemini-flash-1.5",
        "auto":   "anthropic/claude-haiku-4-5",
    }
    or_model = model_map.get(model_choice, "anthropic/claude-haiku-4-5")
    print(f"[LLM] OpenRouter {or_model}")
    return OpenRouterClient(api_key=api_key, model=or_model)


def build_analyzer(mode: str, model_choice: str, env_path: str, prompt_dir: str,
                   priority_chars: list[str] | None = None):
    """
    依 --mode 建立分析器：

      haiku    : OpenRouter Haiku 完整分析（最穩，~0.011 USD/場景）
      free     : OpenRouter 免費模型（無費用，中文品質略差）
      smart    : 智慧路由 — priority 角色(寧凡)用 Haiku，其他用免費模型（省 30-35%）
      hybrid   : 本地 Stage1 篩選 → Haiku 完整分析（需 Ollama，省 15-25%）
      local    : 全本地 Ollama（免費但極慢，8GB RAM 不建議）
      msa      : OpenRouter Haiku + MSA 節省模式（省 45% tokens）
      mock     : 測試用
    """
    from services.llm.openrouter_adapter import OpenRouterClient
    api_key = _load_api_key(env_path)

    if mode == "mock":
        print("[模式] Mock（測試）")
        return FrameworkAnalyzer(llm_client=MockLLMClient(), prompt_dir=prompt_dir)

    if mode == "smart":
        from services.llm.smart_router import SmartRouter
        haiku_llm = OpenRouterClient(api_key=api_key, model="anthropic/claude-haiku-4-5")
        haiku_az  = FrameworkAnalyzer(llm_client=haiku_llm, prompt_dir=prompt_dir)
        chars = priority_chars or ["寧凡"]

        # 優先用 Gemini 免費（若有 key），否則退回 OpenRouter 免費
        gemini_key = _load_gemini_key(env_path)
        if gemini_key:
            from services.llm.gemini_adapter import GeminiClient
            free_llm = GeminiClient(api_key=gemini_key, model="gemini-2.5-flash")
            free_label = "Gemini 2.5 Flash（免費）"
        else:
            free_model = FREE_MODELS.get(model_choice, FREE_MODELS["free-llama"])
            free_llm   = OpenRouterClient(api_key=api_key, model=free_model)
            free_label = f"OpenRouter {free_model}"

        free_az = FrameworkAnalyzer(llm_client=free_llm, prompt_dir=prompt_dir)
        print(f"[模式] Smart 路由 — {chars} → Haiku，其他角色 → {free_label}")
        print(f"        預估省 30-35%% API 費用")
        return SmartRouter(haiku_analyzer=haiku_az, free_analyzer=free_az, priority_chars=chars)

    if mode == "gemini-free":
        gemini_key = _load_gemini_key(env_path)
        if not gemini_key:
            raise ValueError("找不到 GEMINI_API_KEY，請在 .env 加入：GEMINI_API_KEY=your_key")
        from services.llm.gemini_adapter import GeminiClient, GEMINI_FREE_MODELS
        g_model = GEMINI_FREE_MODELS.get(model_choice, "gemini-1.5-flash")
        print(f"[模式] Gemini Free — {g_model}（免費額度，1500 req/day）")
        llm = GeminiClient(api_key=gemini_key, model=g_model)
        return FrameworkAnalyzer(llm_client=llm, prompt_dir=prompt_dir)

    if mode == "hybrid":
        # 本地 Stage1 篩選 + 雲端分析
        if not _ollama_available():
            print("[模式] Hybrid 但 Ollama 不可用 → 改用 haiku 完整模式")
            mode = "haiku"
        else:
            from services.llm.ollama_adapter import OllamaClient
            from services.llm.hybrid_router import HybridAnalyzer
            local = OllamaClient(model="qwen2.5:7b")
            cloud = OpenRouterClient(api_key=api_key, model="anthropic/claude-haiku-4-5")
            print("[模式] Hybrid — 本地 Stage1 篩選 → Haiku Stage2+3")
            print("        預估節省 15-25%% API 費用，每場景 3-8 秒（篩除場景 ~45 秒）")
            return HybridAnalyzer(local_client=local, cloud_client=cloud, prompt_dir=prompt_dir)

    if mode == "free":
        free_model = FREE_MODELS.get(model_choice, FREE_MODELS["free-llama"])
        print(f"[模式] Free — OpenRouter 免費模型 {free_model}")
        print("        無費用，速度快，中文品質比 Haiku 稍差")
        llm = OpenRouterClient(api_key=api_key, model=free_model)
        return FrameworkAnalyzer(llm_client=llm, prompt_dir=prompt_dir)

    if mode == "msa":
        from backend.app.services.msa_analyzer import MSAAnalyzer
        llm = OpenRouterClient(api_key=api_key, model="anthropic/claude-haiku-4-5")
        print("[模式] MSA + Haiku — 省 ~45%% tokens，品質略低於完整版")
        return MSAAnalyzer(llm_client=llm)

    if mode == "local":
        if not _ollama_available():
            print("[模式] Local 但 Ollama 不可用 → 改 haiku")
            mode = "haiku"
        else:
            from services.llm.ollama_adapter import OllamaClient
            from backend.app.services.msa_analyzer import MSAAnalyzer
            print("[模式] Local Ollama（免費，MSA 省 tokens，但慢）")
            return MSAAnalyzer(llm_client=OllamaClient(model="qwen2.5:7b"))

    # 預設：haiku 完整分析
    llm = OpenRouterClient(api_key=api_key, model="anthropic/claude-haiku-4-5")
    print("[模式] Haiku 完整分析（最穩定，~3-8 秒/場景）")
    return FrameworkAnalyzer(llm_client=llm, prompt_dir=prompt_dir)


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
    mode: str,
    model_choice: str,
    skip_existing: bool,
    dry_run: bool,
    concurrency: int,
    priority_chars: list[str] | None = None,
):
    # 初始化 DB
    init_db()
    db = SessionLocal()
    stats = RunStats()
    t0 = time.time()

    # 讀小說
    with open(NOVEL_PATH, encoding="utf-8") as f:
        text = f.read()

    # 建分析器
    env_path = os.path.join(ROOT, ".env")
    prompt_dir = os.path.join(ROOT, "prompts")
    analyzer = build_analyzer(mode, model_choice, env_path, prompt_dir,
                              priority_chars=priority_chars)

    # 取已存在的 (chapter, scene) 組合（用於 skip）
    # 注意：scene_id 是每次執行重新生成的 uuid，不能用於去重
    existing_ch_sc: set[tuple] = set()
    if skip_existing:
        rows = db.query(SceneFrameworkCard.chapter_number, SceneFrameworkCard.scene_number).all()
        existing_ch_sc = {(r[0], r[1]) for r in rows}
        print(f"DB 中已有 {len(existing_ch_sc)} 個場景卡，跳過重複分析")

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
            if (chapter.chapter_number, scene.scene_number) in existing_ch_sc:
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

    # Smart 模式額外印路由統計
    from services.llm.smart_router import SmartRouter
    if isinstance(analyzer, SmartRouter):
        s = analyzer.stats
        print(f"\n[Smart 路由統計]")
        print(f"  Haiku  場景：{s['haiku_scenes']} ({s['haiku_pct']}%)")
        print(f"  Free   場景：{s['free_scenes']} ({100-s['haiku_pct']:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="批次分析《上城之下》",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--chapters", default="1-5",
                        help="章節範圍，如 1-5 或 10-20")
    parser.add_argument("--mode", default="haiku",
                        choices=["haiku", "free", "smart", "gemini-free", "hybrid", "msa", "local", "mock"],
                        help=(
                            "分析模式：\n"
                            "  haiku       : OpenRouter Haiku（最穩，~$0.011/場景）  ← 品質優先\n"
                            "  smart       : 寧凡→Haiku，其他→Gemini免費（省30-35%%）← 推薦\n"
                            "  gemini-free : 全程 Gemini 免費（需 GEMINI_API_KEY，$0）\n"
                            "  free        : OpenRouter 免費模型（需帳戶餘額才能啟用）\n"
                            "  hybrid      : 本地Stage1篩選 → Haiku分析（省15-25%%費用）\n"
                            "  msa         : Haiku + 多階段省token（省45%% tokens）\n"
                            "  local       : 全本地Ollama（免費但極慢，不建議8GB RAM）\n"
                            "  mock        : 測試用"
                        ))
    parser.add_argument("--priority-chars", default="寧凡",
                        help="--mode smart 時哪些角色用 Haiku（逗號分隔，預設：寧凡）")
    parser.add_argument("--free-model", default="free-llama",
                        choices=list(FREE_MODELS.keys()),
                        help="--mode free 時使用哪個免費模型（預設 Llama-3.3-70B，最穩定）")
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳過 DB 中已存在的場景")
    parser.add_argument("--dry-run", action="store_true",
                        help="只切場景 + 角色偵測，不呼叫 LLM")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="同時分析場景數（haiku/free 建議3-5，hybrid/local 建議1-2）")
    args = parser.parse_args()

    parts = args.chapters.split("-")
    start = int(parts[0])
    end   = int(parts[1]) if len(parts) > 1 else start

    priority_chars = [c.strip() for c in args.priority_chars.split(",") if c.strip()]

    asyncio.run(run(
        chapter_start=start,
        chapter_end=end,
        mode=args.mode,
        model_choice=args.free_model if args.mode in ("free", "smart") else args.mode,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
        priority_chars=priority_chars,
    ))


if __name__ == "__main__":
    main()

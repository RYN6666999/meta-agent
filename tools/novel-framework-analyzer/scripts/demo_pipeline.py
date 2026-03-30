"""
demo_pipeline.py
================
MVP 展示腳本：讀取《上城之下》前 5 章，切場景，印出場景結構。
不需要資料庫，不需要 LLM，純本地跑通。

執行：
    python3 scripts/demo_pipeline.py
    python3 scripts/demo_pipeline.py --chapters 1-10
    python3 scripts/demo_pipeline.py --chapter 3 --verbose
"""

import argparse
import sys
import os

# 加入 project root 到 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.services.scene_splitter import split_novel


NOVEL_PATH = os.path.join(ROOT, "上城之下.txt")
BOOK_ID = "shangchengzhixia-001"


def run(chapter_start: int = 1, chapter_end: int = 5, verbose: bool = False):
    with open(NOVEL_PATH, encoding="utf-8") as f:
        text = f.read()

    print(f"《上城之下》 — 場景切分展示")
    print(f"分析章節：第 {chapter_start} 章 ～ 第 {chapter_end} 章")
    print("=" * 60)

    total_scenes = 0
    for chapter, scenes in split_novel(text, BOOK_ID, chapter_range=(chapter_start, chapter_end)):
        total_scenes += len(scenes)
        print(f"\n【第 {chapter.chapter_number} 章】{chapter.title}")
        print(f"  字數：{chapter.char_count}  |  切出場景：{len(scenes)} 個")

        for scene in scenes:
            flag = ""
            if scene.is_too_short:
                flag = " ⚠️ 偏短"
            elif scene.is_too_long:
                flag = " ⚠️ 偏長"

            chars_str = f"{scene.candidate_characters}" if scene.candidate_characters else "（待LLM提取）"
            print(
                f"  場景 {scene.scene_number:2d} | {scene.char_count:4d}字 "
                f"| {scene.boundary_reason:8s} "
                f"| 候選角色：{chars_str}{flag}"
            )

            if verbose:
                # 印出場景前 150 字
                preview = scene.raw_text[:150].replace("\n", " ")
                print(f"         預覽：{preview}...")
                print()

    print("\n" + "=" * 60)
    print(f"合計：{chapter_end - chapter_start + 1} 章，{total_scenes} 個場景")
    avg = total_scenes / (chapter_end - chapter_start + 1)
    print(f"平均每章 {avg:.1f} 個場景")


def main():
    parser = argparse.ArgumentParser(description="上城之下 場景切分展示")
    parser.add_argument("--chapters", default="1-5", help="章節範圍，如 1-5 或 10-15")
    parser.add_argument("--chapter", type=int, help="單一章節，覆蓋 --chapters")
    parser.add_argument("--verbose", action="store_true", help="顯示場景預覽文字")
    args = parser.parse_args()

    if args.chapter:
        start = end = args.chapter
    else:
        parts = args.chapters.split("-")
        start = int(parts[0])
        end = int(parts[1]) if len(parts) > 1 else start

    run(start, end, args.verbose)


if __name__ == "__main__":
    main()

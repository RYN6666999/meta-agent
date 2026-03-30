"""
scan_characters.py
==================
自動掃描小說前 N 章，統計高頻人名，更新 character_extractor.py 的 KNOWN_CHARACTERS。

執行：
    python3 scripts/scan_characters.py               # 掃前 30 章
    python3 scripts/scan_characters.py --chapters 50 # 掃前 50 章
    python3 scripts/scan_characters.py --dry-run      # 只印結果，不寫入
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.services.scene_splitter import split_chapters

NOVEL_PATH = os.path.join(ROOT, "上城之下.txt")
EXTRACTOR_PATH = os.path.join(ROOT, "backend", "app", "services", "character_extractor.py")

# 必定排除的非人名詞
STOP_WORDS = {
    # 常見動詞/副詞/連詞
    "這時", "此時", "那時", "當時", "突然", "終於", "雖然", "可是", "但是",
    "所以", "因此", "如果", "雖說", "只是", "不過", "然後", "接著", "於是",
    "果然", "竟然", "居然", "似乎", "好像", "當然", "確實", "已經", "還是",
    # 地點/物件
    "下城", "上城", "區外", "廣場", "顯示", "區域", "地方", "門口", "窗口",
    "內區", "外區", "隊長", "隊員", "任務", "考核", "血統", "索拉", "情報",
    # 稱謂（不是名字）
    "老頭", "老人", "小子", "傢伙", "這人", "那人", "眾人", "二人", "兩人",
    # 動作詞組
    "回頭", "點頭", "搖頭", "皺眉", "抬頭", "低頭", "轉身", "起身", "出手",
    # 其他
    "什麼", "怎麼", "為什麼", "哪裡", "這裡", "那裡", "這樣", "那樣",
    # 副詞/形容詞（常接在說話動詞前）
    "淡淡", "輕輕", "緩緩", "靜靜", "悄悄", "慢慢", "快速", "忽然",
    "卻忽", "他卻", "她卻", "卻是", "卻也", "卻又", "輕描",
    # 明確非人名
    "男人", "女人", "老人", "少年", "青年", "中年", "輕聲",
    "寧凡苦", "寧凡默", "寧凡輕",  # 「寧凡苦笑道」被錯誤截取的片段
}

# 前置邊界：名字前必須是標點或行首，避免「寧凡認真道」被截成「寧凡認真」
_BOUNDARY = r"(?:^|(?<=[。，！？、「」『』…\n\r　 ]))"

# 對話歸屬動詞 — 用多字詞組，避免單字「道」誤抓
SPEECH_PATTERN = re.compile(
    _BOUNDARY +
    r"([\u4e00-\u9fff]{2,4})"
    r"(?:說道|說：|問道|答道|喊道|笑道|罵道|嘆道|低聲道|冷聲道|"
    r"皺眉道|沉聲道|輕聲道|冷笑道|苦笑道|微笑道|大笑道|點頭道|搖頭道)",
    re.MULTILINE,
)

# 心理描寫（視角人物）— 加前置邊界
INNER_PATTERN = re.compile(
    _BOUNDARY +
    r"([\u4e00-\u9fff]{2,4})"
    r"(?:心想|心中想|腦海中|感覺到|注意到|意識到|回想起|忽然想起)",
    re.MULTILINE,
)

# 人稱後接空格或特定動詞（最嚴格，只取2-3字）
ACTION_PATTERN = re.compile(
    _BOUNDARY +
    r"([\u4e00-\u9fff]{2,3})"
    r"(?=的臉|的眼|站在|走向|走進|回頭|轉身|開口)",
    re.MULTILINE,
)


def scan_names(text: str) -> Counter:
    scores: Counter = Counter()

    for m in SPEECH_PATTERN.finditer(text):
        name = m.group(1).strip()
        if _valid(name):
            scores[name] += 5

    for m in INNER_PATTERN.finditer(text):
        name = m.group(1).strip()
        if _valid(name):
            scores[name] += 4

    for m in ACTION_PATTERN.finditer(text):
        name = m.group(1).strip()
        if _valid(name):
            scores[name] += 1

    return scores


def _valid(name: str) -> bool:
    if name in STOP_WORDS:
        return False
    if len(name) < 2 or len(name) > 4:
        return False
    # 必須全是漢字
    if not all("\u4e00" <= c <= "\u9fff" for c in name):
        return False
    # 排除含有明顯非人名字符
    bad_chars = set("的地得了著過把被讓給叫向往到從在是有這那")
    if any(c in bad_chars for c in name):
        return False
    return True


def update_extractor(new_names: List[str], dry_run: bool):
    """把新發現的角色名寫入 character_extractor.py"""
    with open(EXTRACTOR_PATH, encoding="utf-8") as f:
        content = f.read()

    # 找到 KNOWN_CHARACTERS 區塊
    pattern = re.compile(
        r'(KNOWN_CHARACTERS\s*=\s*\[)(.*?)(\])',
        re.DOTALL
    )
    m = pattern.search(content)
    if not m:
        print("找不到 KNOWN_CHARACTERS，請手動更新 character_extractor.py")
        return

    existing_raw = m.group(2)
    existing = re.findall(r'"([\u4e00-\u9fff]+)"', existing_raw)
    existing_set = set(existing)

    added = [n for n in new_names if n not in existing_set]
    if not added:
        print("沒有新角色需要新增")
        return

    print(f"\n新增角色：{added}")

    if dry_run:
        print("[dry-run] 不寫入檔案")
        return

    # 重建列表（保持原有 + 新增，每行4個）
    all_names = existing + added
    lines = []
    for i in range(0, len(all_names), 4):
        chunk = all_names[i:i+4]
        lines.append("    " + ", ".join(f'"{n}"' for n in chunk) + ",")
    new_block = "\n".join(lines)

    new_content = pattern.sub(
        lambda _: f"KNOWN_CHARACTERS = [\n{new_block}\n]",
        content
    )
    with open(EXTRACTOR_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"✅ character_extractor.py 已更新，共 {len(all_names)} 個已知角色")


def main():
    parser = argparse.ArgumentParser(description="掃描小說人名並更新角色列表")
    parser.add_argument("--chapters", type=int, default=30, help="掃描前N章")
    parser.add_argument("--top", type=int, default=30, help="取前N個高頻名字")
    parser.add_argument("--min-score", type=int, default=15, help="最低分數閾值")
    parser.add_argument("--dry-run", action="store_true", help="只印結果不修改檔案")
    args = parser.parse_args()

    print(f"掃描《上城之下》前 {args.chapters} 章...")

    with open(NOVEL_PATH, encoding="utf-8") as f:
        text = f.read()

    chapters = [
        c for c in split_chapters(text, "scan")
        if c.chapter_number <= args.chapters
    ]
    print(f"取得 {len(chapters)} 個章節")

    total_scores: Counter = Counter()
    for ch in chapters:
        total_scores.update(scan_names(ch.raw_text))

    # 過濾 + 排序
    qualified = [
        (name, score)
        for name, score in total_scores.most_common(args.top * 3)
        if score >= args.min_score
    ][:args.top]

    print(f"\n高頻人名 Top {len(qualified)}（分數={計分規則}）")
    print(f"{'排名':>4}  {'名字':8}  {'分數':>6}")
    print("-" * 25)
    for i, (name, score) in enumerate(qualified, 1):
        print(f"{i:4d}  {name:8}  {score:6d}")

    confirmed = [name for name, _ in qualified]
    update_extractor(confirmed, args.dry_run)


計分規則 = "對話=5, 心理=4, 動作=1"

if __name__ == "__main__":
    main()

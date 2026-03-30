"""
scene_splitter.py
=================
中文小說章節與場景切分器。

切分策略：
1. 章節切分：正則比對「第N章標題」行
2. 場景切分（章節內）：依以下規則偵測場景邊界
   - 空行分隔的段落群（3 個以上連續空行視為強邊界）
   - 時間跳轉詞（次日、數日後、幾天後...）
   - 地點轉換詞（與此同時、另一邊、XX城...）
   - 視角切換（換角色敘事）
   - 對話密集區轉換為旁白（節奏改變）

每個場景保留：
- 原文文字（完整）
- 在章節中的位置（start_line, end_line）
- 估算主要角色（出現次數最多的名詞）
- 場景長度（字數）
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RawChapter:
    """從原文切出的章節"""
    chapter_id: str
    book_id: str
    chapter_number: int
    title: str
    raw_text: str
    start_line: int
    end_line: int
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.raw_text)


@dataclass
class RawScene:
    """從章節切出的場景"""
    scene_id: str
    chapter_id: str
    book_id: str
    chapter_number: int
    scene_number: int          # 在章節中的序號（從 1 起）
    raw_text: str
    start_line: int            # 相對於章節起始行的行號
    end_line: int
    char_count: int = 0
    candidate_characters: List[str] = field(default_factory=list)
    boundary_reason: str = ""  # 為何在此切分，debug 用

    def __post_init__(self):
        self.char_count = len(self.raw_text)

    @property
    def is_too_short(self) -> bool:
        return self.char_count < 150

    @property
    def is_too_long(self) -> bool:
        return self.char_count > 3000


# ---------------------------------------------------------------------------
# 章節切分器
# ---------------------------------------------------------------------------

# 章節標題規則（依優先序）
CHAPTER_TITLE_PATTERNS = [
    re.compile(r'^第\d+章\s*(.+)'),           # 第1章落選
    re.compile(r'^第[零一二三四五六七八九十百千萬]+章\s*(.+)'),  # 第一章...
    re.compile(r'^【第\d+章\s*(.+)】'),        # 【第1章...】
    re.compile(r'^chapter\s+\d+', re.IGNORECASE),
]

# 分隔行標記（非內容行，跳過）
SEPARATOR_PATTERNS = [
    re.compile(r'^-{3,}'),
    re.compile(r'^={3,}'),
    re.compile(r'^第.+章節內容開始'),
    re.compile(r'^愛.+電子書'),
    re.compile(r'^https?://'),
]


def is_chapter_title(line: str) -> Optional[Tuple[int, str]]:
    """
    判斷是否為章節標題行。
    Returns: (chapter_number, title) 或 None
    """
    stripped = line.strip()
    if not stripped:
        return None

    # 最常見格式：第N章標題
    m = re.match(r'^第(\d+)章\s*(.*)$', stripped)
    if m:
        return int(m.group(1)), m.group(2).strip() or f"第{m.group(1)}章"

    # 中文數字章號
    cn_digits = "零一二三四五六七八九十百千萬"
    m2 = re.match(rf'^第([{cn_digits}]+)章\s*(.*)$', stripped)
    if m2:
        num = _cn_to_int(m2.group(1))
        return num, m2.group(2).strip() or f"第{m2.group(1)}章"

    return None


def _cn_to_int(s: str) -> int:
    """簡單中文數字轉整數（處理一到九十九）"""
    mapping = {
        "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
        "十": 10, "百": 100, "千": 1000,
    }
    if len(s) == 1:
        return mapping.get(s, 0)
    if s.startswith("十"):
        return 10 + mapping.get(s[1:], 0) if len(s) > 1 else 10
    result = 0
    i = 0
    while i < len(s):
        v = mapping.get(s[i], 0)
        if v >= 10 and i + 1 < len(s):
            next_v = mapping.get(s[i + 1], 1)
            result += v * (next_v if next_v < 10 else 1)
            i += 1
        else:
            result += v
        i += 1
    return result


def split_chapters(
    text: str,
    book_id: str,
    skip_header_lines: int = 6,
) -> List[RawChapter]:
    """
    將整本小說切成章節。

    Args:
        text: 完整小說文字（UTF-8）
        book_id: 書籍 ID
        skip_header_lines: 跳過前 N 行的書頭資訊
    """
    lines = text.splitlines()
    chapters: List[RawChapter] = []

    current_chapter_num: Optional[int] = None
    current_title: Optional[str] = None
    current_start: Optional[int] = None
    current_lines: List[str] = []

    for i, line in enumerate(lines):
        if i < skip_header_lines:
            continue

        # 跳過分隔行
        if any(p.match(line.strip()) for p in SEPARATOR_PATTERNS):
            continue

        chapter_info = is_chapter_title(line)
        if chapter_info:
            # 儲存上一章
            if current_chapter_num is not None and current_lines:
                chapters.append(
                    RawChapter(
                        chapter_id=str(uuid.uuid4()),
                        book_id=book_id,
                        chapter_number=current_chapter_num,
                        title=current_title or "",
                        raw_text="\n".join(current_lines).strip(),
                        start_line=current_start,
                        end_line=i - 1,
                    )
                )

            current_chapter_num, current_title = chapter_info
            current_start = i
            current_lines = []
        elif current_chapter_num is not None:
            current_lines.append(line)

    # 最後一章
    if current_chapter_num is not None and current_lines:
        chapters.append(
            RawChapter(
                chapter_id=str(uuid.uuid4()),
                book_id=book_id,
                chapter_number=current_chapter_num,
                title=current_title or "",
                raw_text="\n".join(current_lines).strip(),
                start_line=current_start,
                end_line=len(lines) - 1,
            )
        )

    return chapters


# ---------------------------------------------------------------------------
# 場景切分器
# ---------------------------------------------------------------------------

# 時間轉換詞 → 強場景邊界
TIME_TRANSITION_WORDS = re.compile(
    r"(次日|翌日|第二天|數日後|幾天後|一天後|三天後|一個月後|多日後"
    r"|幾個月後|一年後|多年後|那天晚上|翌晨|黎明|清晨|深夜|半夜"
    r"|與此同時|就在這時|就在此時|此時此刻|話說回來)"
)

# 地點轉換詞 → 弱場景邊界
LOCATION_TRANSITION_WORDS = re.compile(
    r"(另一邊|另一方面|與此同時|話說|卻說|再說|且說)"
)

# 對話行的判定（以「或『開頭）
DIALOGUE_LINE = re.compile(r"^\s*[「『「【]")

# 全空行
EMPTY_LINE = re.compile(r"^\s*$")

# 段落縮排（以全形空格或兩個半形空格開頭）
PARAGRAPH_START = re.compile(r"^[\u3000\s]{1,4}\S")


def split_scenes(
    chapter: RawChapter,
    min_scene_chars: int = 200,
    max_scene_chars: int = 2500,
    merge_short_scenes: bool = True,
) -> List[RawScene]:
    """
    將單一章節切成場景列表。

    切分策略：
    1. 空行群（連續 2 行以上空行）作為候選邊界
    2. 時間轉換詞強制切分
    3. 過短場景（< min_scene_chars）合併到前一個場景
    4. 過長場景（> max_scene_chars）在段落邊界細切
    """
    lines = chapter.raw_text.splitlines()
    scenes: List[RawScene] = []

    # Step 1: 切出候選場景塊（依空行群）
    blocks: List[Tuple[int, int, str]] = []  # (start_line, end_line, text)
    current_block_start = 0
    current_block_lines: List[str] = []
    consecutive_empty = 0

    for i, line in enumerate(lines):
        if EMPTY_LINE.match(line):
            consecutive_empty += 1
            current_block_lines.append(line)
        else:
            # 連續 2 個以上空行 → 候選場景邊界
            if consecutive_empty >= 2 and current_block_lines:
                block_text = "\n".join(current_block_lines).strip()
                if block_text:
                    blocks.append((current_block_start, i - 1, block_text))
                current_block_start = i
                current_block_lines = [line]
            else:
                current_block_lines.append(line)
            consecutive_empty = 0

    # 最後一塊
    if current_block_lines:
        block_text = "\n".join(current_block_lines).strip()
        if block_text:
            blocks.append((current_block_start, len(lines) - 1, block_text))

    # 若無法依空行切分（整章幾乎沒空行），改用段落數切分
    if len(blocks) <= 1:
        blocks = _split_by_paragraph_count(lines, target_size=800)

    # Step 2: 在每個 block 內部偵測時間轉換詞，進一步細切
    refined_blocks: List[Tuple[int, int, str, str]] = []  # + boundary_reason
    for start, end, text in blocks:
        sub_blocks = _split_by_time_transition(start, text)
        refined_blocks.extend(sub_blocks)

    # Step 3: 合併過短 blocks
    if merge_short_scenes:
        refined_blocks = _merge_short_blocks(refined_blocks, min_scene_chars)

    # Step 4: 細切過長 blocks
    final_blocks: List[Tuple[int, int, str, str]] = []
    for start, end, text, reason in refined_blocks:
        if len(text) > max_scene_chars:
            sub = _split_long_block(start, text, max_scene_chars)
            final_blocks.extend(sub)
        else:
            final_blocks.append((start, end, text, reason))

    # Step 5: 建立 RawScene 物件
    for idx, (start, end, text, reason) in enumerate(final_blocks, 1):
        if not text.strip():
            continue
        scene = RawScene(
            scene_id=str(uuid.uuid4()),
            chapter_id=chapter.chapter_id,
            book_id=chapter.book_id,
            chapter_number=chapter.chapter_number,
            scene_number=idx,
            raw_text=text.strip(),
            start_line=start,
            end_line=end,
            boundary_reason=reason or "空行邊界",
            candidate_characters=_extract_candidate_characters(text),
        )
        scenes.append(scene)

    return scenes if scenes else [_chapter_as_single_scene(chapter)]


def _split_by_time_transition(
    base_start: int, text: str
) -> List[Tuple[int, int, str, str]]:
    """在 text 內部依時間轉換詞切分"""
    lines = text.splitlines()
    blocks = []
    current_lines = []
    current_start = base_start

    for i, line in enumerate(lines):
        if TIME_TRANSITION_WORDS.search(line) and current_lines:
            blocks.append((
                current_start,
                base_start + i - 1,
                "\n".join(current_lines),
                "時間轉換詞",
            ))
            current_start = base_start + i
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        blocks.append((
            current_start,
            base_start + len(lines) - 1,
            "\n".join(current_lines),
            "章節末尾",
        ))

    return blocks


def _merge_short_blocks(
    blocks: List[Tuple[int, int, str, str]], min_chars: int
) -> List[Tuple[int, int, str, str]]:
    """將過短的 block 合併到前一個"""
    if not blocks:
        return []
    merged = [blocks[0]]
    for start, end, text, reason in blocks[1:]:
        prev_start, prev_end, prev_text, prev_reason = merged[-1]
        if len(text) < min_chars:
            # 合併到前一個
            merged[-1] = (
                prev_start,
                end,
                prev_text + "\n" + text,
                prev_reason,
            )
        else:
            merged.append((start, end, text, reason))
    return merged


def _split_long_block(
    base_start: int, text: str, max_chars: int
) -> List[Tuple[int, int, str, str]]:
    """在段落邊界細切過長 block"""
    lines = text.splitlines()
    blocks = []
    current_lines = []
    current_chars = 0
    current_start = base_start

    for i, line in enumerate(lines):
        current_lines.append(line)
        current_chars += len(line)

        # 在段落邊界切分
        if current_chars >= max_chars and PARAGRAPH_START.match(line):
            blocks.append((
                current_start,
                base_start + i,
                "\n".join(current_lines),
                "長段落切分",
            ))
            current_start = base_start + i + 1
            current_lines = []
            current_chars = 0

    if current_lines:
        blocks.append((
            current_start,
            base_start + len(lines) - 1,
            "\n".join(current_lines),
            "長段落末尾",
        ))

    return blocks


def _split_by_paragraph_count(
    lines: List[str], target_size: int = 800
) -> List[Tuple[int, int, str]]:
    """備用：依字數目標切分（無明顯空行時使用）"""
    blocks = []
    current_lines = []
    current_chars = 0
    current_start = 0

    for i, line in enumerate(lines):
        current_lines.append(line)
        current_chars += len(line)
        if current_chars >= target_size and PARAGRAPH_START.match(line):
            blocks.append((current_start, i, "\n".join(current_lines)))
            current_start = i + 1
            current_lines = []
            current_chars = 0

    if current_lines:
        blocks.append((current_start, len(lines) - 1, "\n".join(current_lines)))

    return blocks


def _extract_candidate_characters(text: str) -> List[str]:
    """
    從場景文字中提取候選角色名。
    策略：找出引號前後的稱呼、2-3 字專名（頻次 >= 2 的）。
    這是粗略估算，正式角色提取由 LLM 完成。
    """
    # 常見人名模式（2-4 個漢字，前後有特定符號或換行）
    candidates: dict[str, int] = {}

    # 對話歸屬：「XXX說」「XXX道」「XXX問」
    for m in re.finditer(r"[\u4e00-\u9fff]{2,4}(?:說|道|問|答|笑道|喊道|低聲道)", text):
        name = m.group(0)[:-1]  # 去掉「說/道/問」
        if 2 <= len(name) <= 4:
            candidates[name] = candidates.get(name, 0) + 1

    # 返回出現 >= 2 次的候選
    return [name for name, count in sorted(candidates.items(), key=lambda x: -x[1]) if count >= 2][:5]


def _chapter_as_single_scene(chapter: RawChapter) -> RawScene:
    """當章節無法切分時，整章作為一個場景"""
    return RawScene(
        scene_id=str(uuid.uuid4()),
        chapter_id=chapter.chapter_id,
        book_id=chapter.book_id,
        chapter_number=chapter.chapter_number,
        scene_number=1,
        raw_text=chapter.raw_text,
        start_line=0,
        end_line=chapter.end_line - chapter.start_line,
        boundary_reason="整章單一場景",
    )


# ---------------------------------------------------------------------------
# 便利函數：一次性切分整本書
# ---------------------------------------------------------------------------

def split_novel(
    text: str,
    book_id: str,
    chapter_range: Optional[Tuple[int, int]] = None,
) -> Iterator[Tuple[RawChapter, List[RawScene]]]:
    """
    切分整本小說，逐章 yield (chapter, scenes)。

    Args:
        text: 完整小說文字
        book_id: 書籍 ID
        chapter_range: 可選，只切 (start_chapter, end_chapter) 範圍（含）
    """
    chapters = split_chapters(text, book_id)

    for chapter in chapters:
        if chapter_range:
            lo, hi = chapter_range
            if not (lo <= chapter.chapter_number <= hi):
                continue

        scenes = split_scenes(chapter)
        yield chapter, scenes

"""
character_extractor.py
=======================
場景主角自動偵測。不呼叫 LLM，純規則。

策略（依優先序）：
1. 對話歸屬：「X說/道/問/答/喊/笑道」→ X 最可能是場景核心人物
2. 心理描寫：「X心想/想到/感到/發現」→ 視角人物
3. 動作頻率：出現次數最多的 2-4 字人名
4. 已知角色名單優先匹配（避免把「林川」切成「川」）
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional, Tuple

# 已知核心角色（隨分析深入可持續擴充）
KNOWN_CHARACTERS = [
    "寧凡", "林川", "輝子", "胖子",
    "小眼鏡", "彩姐", "凌墨", "李天道",
    "孫文輝", "喬菲", "溫彩", "徐賁",
]

# 對話歸屬動詞
SPEECH_VERBS = re.compile(
    r"([\u4e00-\u9fff]{1,4})(?:說道?|道|問道?|答道?|喊道?|笑道?|低聲道?|冷聲道?|皺眉道?|沉聲道?|輕聲道?)"
)

# 心理/視角動詞
INNER_VERBS = re.compile(
    r"([\u4e00-\u9fff]{1,4})(?:心想|想到|感到|注意到|發現|看到|聽到|回憶起|意識到)"
)

# 通用人名模式（2-4 漢字，排除常見非人名詞）
NON_NAME_WORDS = {
    "這時", "此時", "那時", "當時", "突然", "終於", "雖然",
    "只是", "可是", "但是", "所以", "因此", "如果", "雖說",
    "下城", "上城", "區外", "廣場", "顯示",
}


def extract_characters(scene_text: str) -> Tuple[str, List[str]]:
    """
    從場景文字中提取角色。
    Returns:
        (focal_character, secondary_characters)
        focal_character: 最可能的核心視角人物
        secondary_characters: 其他出現的角色
    """
    scores: Counter = Counter()

    # 1. 對話歸屬（權重 3）
    for m in SPEECH_VERBS.finditer(scene_text):
        name = _clean_name(m.group(1))
        if name:
            scores[name] += 3

    # 2. 心理/視角動詞（權重 5，視角人物最重要）
    for m in INNER_VERBS.finditer(scene_text):
        name = _clean_name(m.group(1))
        if name:
            scores[name] += 5

    # 3. 對已知角色做全文頻次統計（權重 2）
    for char in KNOWN_CHARACTERS:
        count = scene_text.count(char)
        if count > 0:
            scores[char] += count * 2

    # 4. 通用人名頻次（權重 1，僅補充）
    for m in re.finditer(r"[\u4e00-\u9fff]{2,4}", scene_text):
        word = m.group(0)
        if word not in NON_NAME_WORDS and _looks_like_name(word):
            scores[word] += 1

    if not scores:
        return "未知", []

    ranked = scores.most_common()
    focal = ranked[0][0]
    secondary = [name for name, _ in ranked[1:6] if name != focal]

    return focal, secondary


def _clean_name(raw: str) -> Optional[str]:
    """清理提取到的名字，去除非人名字符"""
    # 去除單字（太短，通常不是名字）
    if len(raw) < 2:
        return None
    if raw in NON_NAME_WORDS:
        return None
    # 優先用已知角色名匹配（避免「寧凡站在」被切成「寧凡站」）
    for known in KNOWN_CHARACTERS:
        if known in raw or raw in known:
            return known
    return raw if len(raw) <= 4 else None


def _looks_like_name(word: str) -> bool:
    """粗略判斷是否像人名（啟發式）"""
    # 排除含有常見非名字字符的詞
    non_name_chars = set("的地得了著過把被讓給叫向往到從在是有")
    if any(c in non_name_chars for c in word):
        return False
    # 已知角色名直接通過
    if word in KNOWN_CHARACTERS:
        return True
    # 2字詞比3字詞更可能是名字
    return len(word) in (2, 3)

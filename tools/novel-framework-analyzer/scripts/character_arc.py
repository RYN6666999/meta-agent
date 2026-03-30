#!/usr/bin/env python3
"""
character_arc.py — 角色心態弧線視覺化工具

用法:
    python3 scripts/character_arc.py --char 寧凡 --ascii
    python3 scripts/character_arc.py --char 寧凡 --html
    python3 scripts/character_arc.py --compare 寧凡 林川 --html
    python3 scripts/character_arc.py --compare 寧凡 林川 --ascii
"""

import sys
import os
import json
import argparse
from pathlib import Path
from collections import defaultdict

# ROOT = 腳本上兩層目錄
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

TOOL_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOL_ROOT / "novel_analyzer.db"
OUTPUT_DIR = TOOL_ROOT / "output"

# mind_shift_type 強度映射
INTENSITY_MAP = {
    "none": 0,
    "emotion": 1,
    "stance": 2,
    "strategy": 3,
    "values": 4,
    "identity": 5,
}

# match_level 簡碼
MATCH_CODE = {
    "full": "F",
    "partial": "P",
    "weak": "W",
    "none": ".",
    None: ".",
    "": ".",
}

# ASCII 柱狀字元（8級）
BAR_CHARS = "▁▂▃▄▅▆▇█"

# HTML 顏色（各 mind_shift_type）
TYPE_COLORS = {
    "none": "#94a3b8",
    "emotion": "#60a5fa",
    "stance": "#34d399",
    "strategy": "#fbbf24",
    "values": "#f97316",
    "identity": "#e879f9",
}

TYPE_LABELS_ZH = {
    "none": "無心變",
    "emotion": "情緒",
    "stance": "立場",
    "strategy": "策略",
    "values": "價值觀",
    "identity": "身份認同",
}


# ---------------------------------------------------------------------------
# 資料存取
# ---------------------------------------------------------------------------

def load_sqlalchemy():
    """嘗試匯入 sqlalchemy；若無則 fallback 用 sqlite3。"""
    try:
        from sqlalchemy import create_engine, text
        return create_engine(f"sqlite:///{DB_PATH}"), text
    except ImportError:
        return None, None


def fetch_character_scenes(character: str) -> list[dict]:
    """從 scene_framework_cards 拉取指定角色的所有場景，按章節/場景排序。"""
    engine, text_fn = load_sqlalchemy()

    sql = """
        SELECT
            chapter_number,
            scene_number,
            focal_character,
            mind_shift_type,
            confidence_score,
            match_level,
            mind_shift,
            judgment
        FROM scene_framework_cards
        WHERE focal_character = :char
        ORDER BY chapter_number, scene_number
    """

    rows = []
    if engine is not None:
        with engine.connect() as conn:
            result = conn.execute(text_fn(sql), {"char": character})
            for row in result:
                rows.append(_row_to_dict(row))
    else:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql.replace(":char", "?"), (character,))
        for row in cur.fetchall():
            rows.append(_row_to_dict(row))
        conn.close()

    return rows


def _parse_json_field(val):
    """安全解析 JSON 欄位（可能已是 dict 或 str）。"""
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def _row_to_dict(row) -> dict:
    """將 DB row 轉為標準化 dict。"""
    try:
        # sqlalchemy Row
        chapter_number = row.chapter_number
        scene_number = row.scene_number
        focal_character = row.focal_character
        mind_shift_type = row.mind_shift_type
        confidence_score = row.confidence_score
        match_level = row.match_level
        mind_shift = row.mind_shift
        judgment = row.judgment
    except AttributeError:
        # sqlite3.Row（tuple-like）
        chapter_number, scene_number, focal_character, mind_shift_type, \
            confidence_score, match_level, mind_shift, judgment = (
                row["chapter_number"], row["scene_number"], row["focal_character"],
                row["mind_shift_type"], row["confidence_score"], row["match_level"],
                row["mind_shift"], row["judgment"],
            )

    mind_shift_type = (mind_shift_type or "none").lower()
    intensity = INTENSITY_MAP.get(mind_shift_type, 0)
    ms_data = _parse_json_field(mind_shift)
    jd_data = _parse_json_field(judgment)

    return {
        "chapter": chapter_number,
        "scene": scene_number,
        "character": focal_character,
        "type": mind_shift_type,
        "intensity": intensity,
        "confidence": confidence_score or 0.0,
        "match_level": (match_level or "").lower(),
        "before_mindset": ms_data.get("before_mindset", ""),
        "trigger_event": ms_data.get("trigger_event", ""),
        "after_mindset": ms_data.get("after_mindset", ""),
        "shift_description": ms_data.get("shift_description", ""),
        "reasoning": jd_data.get("reasoning", ""),
    }


# ---------------------------------------------------------------------------
# 聚合：每章取最高強度場景
# ---------------------------------------------------------------------------

def aggregate_by_chapter(scenes: list[dict]) -> list[dict]:
    """每章保留強度最高的場景（用於折線圖主線）。"""
    chapter_map: dict[int, dict] = {}
    for s in scenes:
        ch = s["chapter"]
        if ch not in chapter_map or s["intensity"] > chapter_map[ch]["intensity"]:
            chapter_map[ch] = s
    return [chapter_map[ch] for ch in sorted(chapter_map)]


# ---------------------------------------------------------------------------
# ASCII 模式
# ---------------------------------------------------------------------------

def render_ascii(character: str, scenes: list[dict]):
    """在終端印出 ASCII 弧線圖。"""
    if not scenes:
        print(f"[character_arc] 找不到角色「{character}」的場景資料。")
        print(f"[character_arc] DB 路徑：{DB_PATH}")
        return

    chapter_data = aggregate_by_chapter(scenes)
    chapters = [d["chapter"] for d in chapter_data]
    intensities = [d["intensity"] for d in chapter_data]

    max_intensity = 5  # identity = 5
    bar_levels = len(BAR_CHARS)  # 8

    print(f"\n{'='*60}")
    print(f"  角色心態弧線：{character}")
    print(f"{'='*60}")
    print(f"  強度軸：0=none  1=emotion  2=stance  3=strategy  4=values  5=identity")
    print(f"  match: F=full  P=partial  W=weak  .=none")
    print()

    # 縱軸由上到下（5→0）
    for level in range(max_intensity, -1, -1):
        label_map = {5: "identity(5)", 4: "values  (4)", 3: "strategy(3)",
                     2: "stance  (2)", 1: "emotion (1)", 0: "none    (0)"}
        row_label = label_map.get(level, f"level {level}")
        row = f"  {row_label} │"
        for d in chapter_data:
            bar_idx = int(d["intensity"] / max_intensity * (bar_levels - 1))
            if d["intensity"] >= level:
                char = BAR_CHARS[bar_idx] if level == 0 else "█"
                row += f" {char}"
            else:
                row += "  "
        print(row)

    # 橫軸
    separator = "  " + " " * 12 + "┼" + "──" * len(chapter_data)
    print(separator)
    ch_row = "  " + " " * 12 + " "
    for d in chapter_data:
        ch_row += f"{d['chapter']:2}"
    print(ch_row)
    print("  " + " " * 13 + "章節")

    # match_level 行
    print()
    match_row = "  match_level      │"
    for d in chapter_data:
        code = MATCH_CODE.get(d["match_level"], ".")
        match_row += f" {code}"
    print(match_row)

    # 強度值行
    intensity_row = "  強度              │"
    for d in chapter_data:
        intensity_row += f" {d['intensity']}"
    print(intensity_row)

    print()
    print("  場景詳情：")
    print(f"  {'章':>3} {'場':>3} {'類型':<10} {'強度':>3} {'match':>5}  before → after")
    print(f"  {'─'*3} {'─'*3} {'─'*10} {'─'*3} {'─'*5}  {'─'*40}")
    for s in scenes:
        before = (s["before_mindset"] or "")[:20]
        after = (s["after_mindset"] or "")[:20]
        arrow = f"{before} → {after}" if before or after else ""
        print(f"  {s['chapter']:>3} {s['scene']:>3} {s['type']:<10} {s['intensity']:>3} "
              f"{MATCH_CODE.get(s['match_level'], '.'):>5}  {arrow}")

    print(f"\n{'='*60}\n")


def render_ascii_compare(char1: str, scenes1: list[dict], char2: str, scenes2: list[dict]):
    """並排比較兩個角色的 ASCII 弧線。"""
    print(f"\n{'='*60}")
    print(f"  角色弧線比較：{char1} vs {char2}")
    print(f"{'='*60}\n")
    print(f"  ── {char1} ──")
    render_ascii(char1, scenes1)
    print(f"  ── {char2} ──")
    render_ascii(char2, scenes2)


# ---------------------------------------------------------------------------
# HTML 模式
# ---------------------------------------------------------------------------

def _escape(s: str) -> str:
    """HTML 轉義。"""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def build_html(characters: list[str], all_scenes: dict[str, list[dict]]) -> str:
    """生成完全自包含的 HTML 視覺化頁面。"""

    # 收集所有章節範圍
    all_chapters: set[int] = set()
    char_chapter_data: dict[str, list[dict]] = {}
    for char in characters:
        scenes = all_scenes.get(char, [])
        agg = aggregate_by_chapter(scenes)
        char_chapter_data[char] = agg
        for d in agg:
            all_chapters.add(d["chapter"])

    if not all_chapters:
        min_ch, max_ch = 1, 1
    else:
        min_ch = min(all_chapters)
        max_ch = max(all_chapters)

    title = "角色心態弧線" + (" — " + " vs ".join(characters) if len(characters) > 1 else f" — {characters[0]}")

    # SVG 折線圖參數
    svg_w = max(800, (max_ch - min_ch + 2) * 60)
    svg_h = 360
    pad_l = 80
    pad_r = 40
    pad_t = 30
    pad_b = 60
    plot_w = svg_w - pad_l - pad_r
    plot_h = svg_h - pad_t - pad_b
    max_intensity = 5

    def ch_to_x(ch: int) -> float:
        if max_ch == min_ch:
            return pad_l + plot_w / 2
        return pad_l + (ch - min_ch) / (max_ch - min_ch) * plot_w

    def intensity_to_y(intensity: float) -> float:
        return pad_t + plot_h - (intensity / max_intensity) * plot_h

    # 多角色顏色
    char_line_colors = ["#6366f1", "#f43f5e", "#10b981", "#f59e0b"]

    svg_parts = []

    # 格線
    for lvl in range(0, max_intensity + 1):
        y = intensity_to_y(lvl)
        label_map_svg = {0: "none(0)", 1: "emotion(1)", 2: "stance(2)",
                         3: "strategy(3)", 4: "values(4)", 5: "identity(5)"}
        svg_parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#64748b">{label_map_svg.get(lvl, lvl)}</text>'
        )

    # 章節 x 軸刻度
    for ch in range(min_ch, max_ch + 1):
        x = ch_to_x(ch)
        svg_parts.append(
            f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + plot_h}" '
            f'stroke="#f1f5f9" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="{x:.1f}" y="{pad_t + plot_h + 20}" text-anchor="middle" '
            f'font-size="11" fill="#64748b">第{ch}章</text>'
        )

    # 軸線
    svg_parts.append(
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" '
        f'stroke="#cbd5e1" stroke-width="1.5"/>'
    )
    svg_parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" '
        f'stroke="#cbd5e1" stroke-width="1.5"/>'
    )

    # 為每個角色畫折線 + 點
    for ci, char in enumerate(characters):
        line_color = char_line_colors[ci % len(char_line_colors)]
        agg = char_chapter_data.get(char, [])
        if not agg:
            continue

        # 折線
        points = []
        for d in agg:
            x = ch_to_x(d["chapter"])
            y = intensity_to_y(d["intensity"])
            points.append(f"{x:.1f},{y:.1f}")

        if len(points) > 1:
            svg_parts.append(
                f'<polyline points="{" ".join(points)}" fill="none" '
                f'stroke="{line_color}" stroke-width="2.5" stroke-linejoin="round" '
                f'stroke-linecap="round" opacity="0.85"/>'
            )

        # 點（帶 tooltip）
        for d in agg:
            x = ch_to_x(d["chapter"])
            y = intensity_to_y(d["intensity"])
            color = TYPE_COLORS.get(d["type"], "#94a3b8")
            before = _escape(d["before_mindset"] or "—")
            trigger = _escape(d["trigger_event"] or "—")
            after = _escape(d["after_mindset"] or "—")
            shift_desc = _escape(d["shift_description"] or "—")
            tooltip_id = f"tip_{ci}_{d['chapter']}_{d['scene']}"

            svg_parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}" '
                f'stroke="white" stroke-width="2" '
                f'class="dot" '
                f'data-char="{_escape(char)}" '
                f'data-ch="{d["chapter"]}" '
                f'data-sc="{d["scene"]}" '
                f'data-type="{_escape(d["type"])}" '
                f'data-before="{before}" '
                f'data-trigger="{trigger}" '
                f'data-after="{after}" '
                f'data-desc="{shift_desc}" '
                f'data-intensity="{d["intensity"]}" '
                f'/>'
            )

    svg_content = "\n".join(svg_parts)

    # 圖例
    legend_parts = []
    for char, ci in [(c, i) for i, c in enumerate(characters)]:
        color = char_line_colors[ci % len(char_line_colors)]
        legend_parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;">'
            f'<svg width="20" height="4"><line x1="0" y1="2" x2="20" y2="2" '
            f'stroke="{color}" stroke-width="2.5"/></svg>'
            f'<span>{_escape(char)}</span></span>'
        )
    for t_type, color in TYPE_COLORS.items():
        legend_parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;">'
            f'<svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="{color}"/></svg>'
            f'<span>{TYPE_LABELS_ZH.get(t_type, t_type)}</span></span>'
        )
    legend_html = "\n".join(legend_parts)

    # 場景摘要表格（所有角色）
    table_rows = []
    for char in characters:
        scenes = all_scenes.get(char, [])
        for s in scenes:
            ms_type_label = TYPE_LABELS_ZH.get(s["type"], s["type"])
            type_color = TYPE_COLORS.get(s["type"], "#94a3b8")
            match_code = MATCH_CODE.get(s["match_level"], ".")
            before = _escape(s["before_mindset"] or "—")
            trigger = _escape(s["trigger_event"] or "—")
            after_ms = _escape(s["after_mindset"] or "—")
            reasoning = _escape(s["reasoning"] or "—")
            table_rows.append(
                f'<tr>'
                f'<td>{_escape(char)}</td>'
                f'<td>{s["chapter"]}</td>'
                f'<td>{s["scene"]}</td>'
                f'<td><span class="badge" style="background:{type_color}">{ms_type_label}</span></td>'
                f'<td>{s["intensity"]}</td>'
                f'<td>{match_code}</td>'
                f'<td>{before}</td>'
                f'<td>{trigger}</td>'
                f'<td>{after_ms}</td>'
                f'<td style="font-size:12px;color:#64748b">{reasoning[:80]}{"…" if len(s["reasoning"] or "") > 80 else ""}</td>'
                f'</tr>'
            )
    table_body = "\n".join(table_rows) if table_rows else '<tr><td colspan="10" style="text-align:center;color:#94a3b8;padding:24px">尚無資料</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape(title)}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC",
                 "Microsoft JhengHei", sans-serif;
    background: #f8fafc;
    color: #1e293b;
    padding: 24px;
}}
h1 {{
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 6px;
    color: #0f172a;
}}
.subtitle {{
    font-size: 13px;
    color: #64748b;
    margin-bottom: 24px;
}}
.card {{
    background: white;
    border-radius: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    padding: 24px;
    margin-bottom: 24px;
}}
.legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 16px;
    font-size: 13px;
    color: #475569;
}}
.dot {{ cursor: pointer; transition: r 0.15s; }}
.dot:hover {{ r: 10; }}
.tooltip {{
    position: fixed;
    background: #1e293b;
    color: white;
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 13px;
    max-width: 340px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    z-index: 999;
    line-height: 1.6;
    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
}}
.tooltip.visible {{ opacity: 1; }}
.tooltip strong {{ color: #93c5fd; }}
.tip-row {{ margin-top: 6px; }}
.tip-label {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
th {{
    background: #f1f5f9;
    color: #475569;
    font-weight: 600;
    padding: 10px 12px;
    text-align: left;
    border-bottom: 2px solid #e2e8f0;
    white-space: nowrap;
}}
td {{
    padding: 9px 12px;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: top;
}}
tr:hover td {{ background: #f8fafc; }}
.badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 9999px;
    font-size: 11px;
    color: white;
    font-weight: 600;
    white-space: nowrap;
}}
svg text {{ user-select: none; }}
</style>
</head>
<body>

<h1>{_escape(title)}</h1>
<p class="subtitle">資料來源：{_escape(str(DB_PATH))} &nbsp;|&nbsp; 生成時間：<span id="ts"></span></p>

<div class="card">
    <h2 style="font-size:16px;font-weight:600;margin-bottom:16px;">心態強度時間軸</h2>
    <svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}"
         style="max-width:100%;height:auto;display:block;">
        {svg_content}
    </svg>
    <div class="legend">
        {legend_html}
    </div>
</div>

<div class="card">
    <h2 style="font-size:16px;font-weight:600;margin-bottom:16px;">場景詳細列表</h2>
    <div style="overflow-x:auto;">
    <table>
        <thead>
            <tr>
                <th>角色</th>
                <th>章</th>
                <th>場</th>
                <th>心變類型</th>
                <th>強度</th>
                <th>Match</th>
                <th>前心態</th>
                <th>觸發事件</th>
                <th>後心態</th>
                <th>分析推理</th>
            </tr>
        </thead>
        <tbody>
            {table_body}
        </tbody>
    </table>
    </div>
</div>

<!-- Tooltip -->
<div class="tooltip" id="tooltip"></div>

<script>
document.getElementById("ts").textContent = new Date().toLocaleString("zh-TW");

const tooltip = document.getElementById("tooltip");

document.querySelectorAll(".dot").forEach(dot => {{
    dot.addEventListener("mouseenter", e => {{
        const d = dot.dataset;
        tooltip.innerHTML = `
            <strong>${{d.char}} — 第${{d.ch}}章 第${{d.sc}}場</strong>
            <div class="tip-row"><span class="tip-label">心變類型</span><br>${{d.type}}（強度 ${{d.intensity}}）</div>
            <div class="tip-row"><span class="tip-label">前心態</span><br>${{d.before}}</div>
            <div class="tip-row"><span class="tip-label">觸發事件</span><br>${{d.trigger}}</div>
            <div class="tip-row"><span class="tip-label">後心態</span><br>${{d.after}}</div>
            ${{d.desc ? `<div class="tip-row"><span class="tip-label">轉變描述</span><br>${{d.desc}}</div>` : ""}}
        `;
        tooltip.classList.add("visible");
        moveTooltip(e);
    }});
    dot.addEventListener("mousemove", moveTooltip);
    dot.addEventListener("mouseleave", () => {{
        tooltip.classList.remove("visible");
    }});
}});

function moveTooltip(e) {{
    const margin = 14;
    const tw = tooltip.offsetWidth;
    const th = tooltip.offsetHeight;
    let left = e.clientX + margin;
    let top = e.clientY + margin;
    if (left + tw > window.innerWidth - 10) left = e.clientX - tw - margin;
    if (top + th > window.innerHeight - 10) top = e.clientY - th - margin;
    tooltip.style.left = left + "px";
    tooltip.style.top = top + "px";
}}
</script>
</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="角色心態弧線視覺化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--char", metavar="角色名", help="單一角色弧線")
    group.add_argument("--compare", metavar="角色名", nargs=2, help="比較兩個角色弧線")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--ascii", action="store_true", help="終端 ASCII 模式")
    mode_group.add_argument("--html", action="store_true", help="HTML 視覺化（預設）")

    args = parser.parse_args()

    # 確保 output/ 目錄存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 決定角色列表與模式
    if args.char:
        characters = [args.char]
    else:
        characters = args.compare

    use_ascii = args.ascii  # --html 或預設都走 HTML

    # 拉資料
    all_scenes: dict[str, list[dict]] = {}
    for char in characters:
        scenes = fetch_character_scenes(char)
        all_scenes[char] = scenes
        if scenes:
            print(f"[character_arc] 載入「{char}」：{len(scenes)} 個場景")
        else:
            print(f"[character_arc] 警告：找不到角色「{char}」的場景資料（DB 可能尚未分析）")

    if use_ascii:
        if len(characters) == 1:
            render_ascii(characters[0], all_scenes[characters[0]])
        else:
            render_ascii_compare(
                characters[0], all_scenes[characters[0]],
                characters[1], all_scenes[characters[1]],
            )
    else:
        # HTML 模式
        html_content = build_html(characters, all_scenes)
        if len(characters) == 1:
            out_file = OUTPUT_DIR / f"arc_{characters[0]}.html"
        else:
            out_file = OUTPUT_DIR / f"arc_{'_vs_'.join(characters)}.html"

        out_file.write_text(html_content, encoding="utf-8")
        print(f"[character_arc] HTML 已寫入：{out_file}")
        print(f"[character_arc] 用瀏覽器開啟：file://{out_file.resolve()}")


if __name__ == "__main__":
    main()

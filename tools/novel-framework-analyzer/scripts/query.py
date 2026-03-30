#!/usr/bin/env python3
"""
query.py — SQLite 查詢 CLI for novel-framework-analyzer
Usage examples:
  python3 scripts/query.py --char 寧凡
  python3 scripts/query.py --match full
  python3 scripts/query.py --chapter 3
  python3 scripts/query.py --summary
  python3 scripts/query.py --search 欲望
  python3 scripts/query.py --show ch3s2
"""

import sys
import os
import json
import argparse
import sqlite3

# ROOT = two levels up from this script
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB_PATH = os.path.join(ROOT, "novel_analyzer.db")


# ---------------------------------------------------------------------------
# ASCII table helpers
# ---------------------------------------------------------------------------

def _col_widths(headers, rows):
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    return widths


def print_table(headers, rows):
    if not rows:
        print("  (no results)")
        return
    widths = _col_widths(headers, rows)
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    fmt = "| " + " | ".join("{:<" + str(w) + "}" for w in widths) + " |"
    print(sep)
    print(fmt.format(*[str(h) for h in headers]))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print(sep)


def _trunc(text, n=40):
    s = str(text) if text is not None else ""
    return s[:n] + "..." if len(s) > n else s


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_conn():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def _json_text(value):
    """Return a plain-text representation of a JSON field (string or dict/list)."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return " ".join(str(v) for v in parsed.values())
            if isinstance(parsed, list):
                return " ".join(str(v) for v in parsed)
            return str(parsed)
        except (json.JSONDecodeError, TypeError):
            return value
    return str(value)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_char(char_name):
    """List all scenes where focal_character = char_name OR char_name in secondary_characters."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT chapter_number, scene_number, scene_id, focal_character,
               match_level, confidence_score, mind_shift_type
        FROM scene_framework_cards
        WHERE focal_character = ?
           OR secondary_characters LIKE ?
        ORDER BY chapter_number, scene_number
    """, (char_name, f'%{char_name}%'))
    rows = cur.fetchall()
    conn.close()

    headers = ["Ch", "Sc", "scene_id", "focal_char", "match", "conf", "mind_shift_type"]
    table_rows = []
    for r in rows:
        ch, sc, sid, fc, match, conf, mst = r
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        table_rows.append([ch, sc, sid or "", fc or "", match or "", conf_str, mst or ""])

    print(f"\n[角色查詢] focal/secondary = '{char_name}'  共 {len(table_rows)} 筆\n")
    print_table(headers, table_rows)


def cmd_match(match_level):
    """List all scenes with given match_level."""
    valid = {"full", "partial", "weak", "none"}
    if match_level not in valid:
        print(f"[ERROR] match_level 必須是 {valid}", file=sys.stderr)
        sys.exit(1)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT chapter_number, scene_number, scene_id, focal_character,
               confidence_score, mind_shift_type
        FROM scene_framework_cards
        WHERE match_level = ?
        ORDER BY chapter_number, scene_number
    """, (match_level,))
    rows = cur.fetchall()
    conn.close()

    headers = ["Ch", "Sc", "scene_id", "focal_char", "conf", "mind_shift_type"]
    table_rows = []
    for r in rows:
        ch, sc, sid, fc, conf, mst = r
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        table_rows.append([ch, sc, sid or "", fc or "", conf_str, mst or ""])

    print(f"\n[match_level={match_level}] 共 {len(table_rows)} 筆\n")
    print_table(headers, table_rows)


def cmd_chapter(chapter_number):
    """List all scene cards for the given chapter."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT scene_number, scene_id, focal_character,
               match_level, confidence_score, mind_shift_type
        FROM scene_framework_cards
        WHERE chapter_number = ?
        ORDER BY scene_number
    """, (chapter_number,))
    rows = cur.fetchall()
    conn.close()

    headers = ["Sc", "scene_id", "focal_char", "match", "conf", "mind_shift_type"]
    table_rows = []
    for r in rows:
        sc, sid, fc, match, conf, mst = r
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        table_rows.append([sc, sid or "", fc or "", match or "", conf_str, mst or ""])

    print(f"\n[第 {chapter_number} 章] 共 {len(table_rows)} 個場景\n")
    print_table(headers, table_rows)


def cmd_summary():
    """Output global statistics."""
    conn = get_conn()
    cur = conn.cursor()

    # Total scenes
    cur.execute("SELECT COUNT(*) FROM scene_framework_cards")
    total = cur.fetchone()[0]

    # Match distribution
    cur.execute("""
        SELECT match_level, COUNT(*) as cnt
        FROM scene_framework_cards
        GROUP BY match_level
        ORDER BY cnt DESC
    """)
    match_dist = cur.fetchall()

    # Average confidence
    cur.execute("SELECT AVG(confidence_score) FROM scene_framework_cards WHERE confidence_score IS NOT NULL")
    avg_conf = cur.fetchone()[0]

    # Top 5 focal characters
    cur.execute("""
        SELECT focal_character, COUNT(*) as cnt
        FROM scene_framework_cards
        WHERE focal_character IS NOT NULL AND focal_character != ''
        GROUP BY focal_character
        ORDER BY cnt DESC
        LIMIT 5
    """)
    top_chars = cur.fetchall()

    # mind_shift_type distribution
    cur.execute("""
        SELECT mind_shift_type, COUNT(*) as cnt
        FROM scene_framework_cards
        GROUP BY mind_shift_type
        ORDER BY cnt DESC
    """)
    mst_dist = cur.fetchall()

    conn.close()

    print("\n" + "=" * 50)
    print("  全局統計 Summary")
    print("=" * 50)
    print(f"  場景總數: {total}")
    print(f"  平均 confidence: {avg_conf:.3f}" if avg_conf is not None else "  平均 confidence: N/A")

    print("\n  match_level 分布:")
    print_table(["match_level", "count"], [(r[0] or "NULL", r[1]) for r in match_dist])

    print("\n  最常出現角色 Top 5:")
    print_table(["focal_character", "count"], [(r[0], r[1]) for r in top_chars])

    print("\n  mind_shift_type 分布:")
    print_table(["mind_shift_type", "count"], [(r[0] or "NULL", r[1]) for r in mst_dist])

    # Negotiation scene count (need a fresh connection since we already closed)
    conn3 = get_conn()
    cur3 = conn3.cursor()
    cur3.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE is_negotiation_scene = 1")
    nego_count = cur3.fetchone()[0]
    conn3.close()
    print(f"\n  談判場景數: {nego_count} / {total}  (--negotiation 查看詳情)")


def cmd_search(keyword):
    """Search keyword in situation/desire/mind_shift JSON text fields."""
    conn = get_conn()
    cur = conn.cursor()
    # Use LIKE on the raw JSON text stored in the columns
    like = f"%{keyword}%"
    cur.execute("""
        SELECT chapter_number, scene_number, scene_id, focal_character,
               situation, desire, mind_shift, match_level, confidence_score
        FROM scene_framework_cards
        WHERE situation LIKE ?
           OR desire LIKE ?
           OR mind_shift LIKE ?
        ORDER BY chapter_number, scene_number
    """, (like, like, like))
    rows = cur.fetchall()
    conn.close()

    headers = ["Ch", "Sc", "scene_id", "focal_char", "match", "conf", "hit_field(snippet)"]
    table_rows = []
    for r in rows:
        ch, sc, sid, fc, situation, desire, mind_shift, match, conf = r
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        # Identify which field(s) matched and show snippet
        snippets = []
        for field_name, field_val in [("situation", situation), ("desire", desire), ("mind_shift", mind_shift)]:
            text = _json_text(field_val)
            if keyword in text:
                idx = text.find(keyword)
                start = max(0, idx - 15)
                end = min(len(text), idx + len(keyword) + 15)
                snippets.append(f"{field_name}:...{text[start:end]}...")
        table_rows.append([ch, sc, sid or "", fc or "", match or "", conf_str, " | ".join(snippets)])

    print(f"\n[搜尋] keyword='{keyword}'  共 {len(table_rows)} 筆\n")
    print_table(headers, table_rows)


def cmd_show(ref):
    """Show full analysis card for a scene reference like ch3s2."""
    import re
    m = re.match(r"ch(\d+)s(\d+)", ref.lower())
    if not m:
        print("[ERROR] --show 格式必須是 chNsM，例如 ch3s2", file=sys.stderr)
        sys.exit(1)
    chapter_number = int(m.group(1))
    scene_number = int(m.group(2))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, scene_id, book_id, chapter_number, scene_number,
               scene_text, focal_character, secondary_characters,
               situation, desire, mind_shift, judgment,
               match_level, confidence_score, mind_shift_type,
               model_used, prompt_version, created_at
        FROM scene_framework_cards
        WHERE chapter_number = ? AND scene_number = ?
        ORDER BY id
        LIMIT 1
    """, (chapter_number, scene_number))
    row = cur.fetchone()
    conn.close()

    if row is None:
        print(f"[找不到] ch{chapter_number}s{scene_number} 不存在於 DB")
        return

    (rid, scene_id, book_id, ch, sc, scene_text,
     focal_char, secondary_chars, situation, desire,
     mind_shift, judgment, match_level, conf, mst,
     model_used, prompt_version, created_at) = row

    def fmt_json(val, indent=4):
        if val is None:
            return "(null)"
        try:
            parsed = json.loads(val)
            return json.dumps(parsed, ensure_ascii=False, indent=indent)
        except (json.JSONDecodeError, TypeError):
            return str(val)

    conf_str = f"{conf:.3f}" if conf is not None else "N/A"

    border = "=" * 60
    thin = "-" * 60
    print(f"\n{border}")
    print(f"  場景完整分析卡  ch{chapter_number}s{scene_number}")
    print(border)
    print(f"  id            : {rid}")
    print(f"  scene_id      : {scene_id}")
    print(f"  book_id       : {book_id}")
    print(f"  chapter       : {ch}  scene: {sc}")
    print(f"  model_used    : {model_used}")
    print(f"  prompt_version: {prompt_version}")
    print(f"  created_at    : {created_at}")
    print(thin)
    print(f"  match_level   : {match_level}")
    print(f"  confidence    : {conf_str}")
    print(f"  mind_shift_type: {mst}")
    print(thin)
    print(f"  focal_character: {focal_char}")
    print(f"  secondary_characters:")
    try:
        sc_list = json.loads(secondary_chars) if secondary_chars else []
        for c in sc_list:
            print(f"    - {c}")
    except (json.JSONDecodeError, TypeError):
        print(f"    {secondary_chars}")
    print(thin)
    print("  [situation]")
    print(fmt_json(situation))
    print()
    print("  [desire]")
    print(fmt_json(desire))
    print()
    print("  [mind_shift]")
    print(fmt_json(mind_shift))
    print()
    print("  [judgment]")
    print(fmt_json(judgment))
    print(thin)
    print("  [scene_text 原文引用]")
    if scene_text:
        # Show up to 500 chars with line wrapping at 60
        text = scene_text[:500]
        if len(scene_text) > 500:
            text += f"\n  ... (共 {len(scene_text)} 字，截斷至 500)"
        for i in range(0, len(text), 60):
            print(f"  {text[i:i+60]}")
    else:
        print("  (無原文)")
    print(border)


def cmd_negotiation():
    """List all scenes marked as negotiation scenes."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT chapter_number, scene_number, scene_id, focal_character,
               match_level, confidence_score, negotiation_pattern_tags
        FROM scene_framework_cards
        WHERE is_negotiation_scene = 1
        ORDER BY chapter_number, scene_number
    """)
    rows = cur.fetchall()
    conn.close()

    headers = ["Ch", "Sc", "focal_char", "match", "conf", "negotiation_tags"]
    table_rows = []
    for r in rows:
        ch, sc, sid, fc, match, conf, tags = r
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        try:
            tags_parsed = json.loads(tags) if tags else []
            tags_str = ", ".join(tags_parsed[:3]) + ("..." if len(tags_parsed) > 3 else "")
        except Exception:
            tags_str = str(tags or "")
        table_rows.append([ch, sc, fc or "", match or "", conf_str, tags_str])

    print(f"\n[談判場景] 共 {len(table_rows)} 個\n")
    if not table_rows:
        print("  尚無談判場景（需重新分析並使用新版 prompt）")
    else:
        print_table(headers, table_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="novel-framework-analyzer SQLite 查詢 CLI",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--char", metavar="角色名",
                        help="列出該角色的所有場景卡")
    parser.add_argument("--match", metavar="LEVEL",
                        choices=["full", "partial", "weak", "none"],
                        help="列出所有 match_level=LEVEL 的場景")
    parser.add_argument("--chapter", metavar="N", type=int,
                        help="列出第 N 章所有場景卡")
    parser.add_argument("--summary", action="store_true",
                        help="輸出全局統計")
    parser.add_argument("--search", metavar="關鍵字",
                        help="在 situation/desire/mind_shift 中搜尋關鍵字")
    parser.add_argument("--show", metavar="chNsM",
                        help="顯示第N章第M場景的完整分析卡 (例如 ch3s2)")
    parser.add_argument("--negotiation", action="store_true",
                        help="列出所有談判場景")

    args = parser.parse_args()

    if args.char:
        cmd_char(args.char)
    elif args.match:
        cmd_match(args.match)
    elif args.chapter is not None:
        cmd_chapter(args.chapter)
    elif args.summary:
        cmd_summary()
    elif args.search:
        cmd_search(args.search)
    elif args.show:
        cmd_show(args.show)
    elif args.negotiation:
        cmd_negotiation()
    else:
        parser.print_help()

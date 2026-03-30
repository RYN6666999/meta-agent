#!/usr/bin/env python3
"""
review_negotiation.py — 談判場景人工審查 CLI

用途：列出所有 is_negotiation_scene=true 的場景，
      讓使用者逐一確認是否真的是談判場景，
      並可以補充 / 修正 negotiation_pattern_tags。

執行：
    python3 scripts/review_negotiation.py          # 逐一審查
    python3 scripts/review_negotiation.py --list   # 只列表，不審查
    python3 scripts/review_negotiation.py --fix ch3s2  # 手動修正特定場景
"""
import sys, os, json, sqlite3, textwrap, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "novel_analyzer.db")

ALL_TAGS = [
    "low_posture_control", "borrowed_pressure", "let_opponent_speak_first",
    "exchange_probe", "condition_redefinition", "risk_transfer",
    "fake_concession", "weakness_to_initiative", "information_for_space",
    "rule_rewrite", "bluff_detection", "tempo_control",
]


def get_conn():
    return sqlite3.connect(DB_PATH)


def list_negotiation(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT chapter_number, scene_number, focal_character,
               confidence_score, mind_shift_type, negotiation_pattern_tags,
               desire, mind_shift
        FROM scene_framework_cards
        WHERE is_negotiation_scene = 1
        ORDER BY chapter_number, scene_number
    """)
    return cur.fetchall()


def print_scene_brief(row):
    ch, sc, focal, conf, mst, tags_raw, desire_raw, ms_raw = row
    try:
        tags = json.loads(tags_raw) if tags_raw else []
    except Exception:
        tags = []
    try:
        desire = json.loads(desire_raw) if desire_raw else {}
        explicit = desire.get("explicit_desire", "")[:80]
    except Exception:
        explicit = ""
    try:
        ms = json.loads(ms_raw) if ms_raw else {}
        before = ms.get("before_mindset", "")[:60]
        trigger = ms.get("trigger_event", "")[:60]
    except Exception:
        before = trigger = ""

    print(f"\n{'='*60}")
    print(f"  ch{ch} s{sc} | 主角：{focal} | conf={conf:.2f} | {mst}")
    print(f"  談判標籤：{', '.join(tags) if tags else '（無）'}")
    print(f"  欲：{explicit}...")
    print(f"  心(前)：{before}...")
    print(f"  觸發：{trigger}...")


def print_scene_full(ch, sc, conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT focal_character, secondary_characters,
               situation, desire, mind_shift, judgment,
               negotiation_pattern_tags, scene_text
        FROM scene_framework_cards
        WHERE chapter_number=? AND scene_number=?
        LIMIT 1
    """, (ch, sc))
    row = cur.fetchone()
    if not row:
        print("找不到場景")
        return
    focal, sec, sit_raw, des_raw, ms_raw, jdg_raw, tags_raw, text = row

    def jget(raw, *keys, default=""):
        try:
            d = json.loads(raw) if raw else {}
            for k in keys:
                d = d.get(k, {})
            return str(d)[:200] if d else default
        except Exception:
            return default

    print(f"\n{'─'*60}")
    print(f"【局】{jget(sit_raw, 'external_situation')}")
    print(f"   主動方：{jget(sit_raw, 'active_party')}  被動方：{jget(sit_raw, 'passive_party')}")
    print(f"【心】{jget(ms_raw, 'before_mindset')[:120]}")
    print(f"【欲】顯：{jget(des_raw, 'explicit_desire')[:80]}")
    print(f"     隱：{jget(des_raw, 'implicit_desire')[:80]}")
    print(f"【變】觸發：{jget(ms_raw, 'trigger_event')[:100]}")
    print(f"     結果：{jget(ms_raw, 'after_mindset')[:100]}")
    print(f"\n【原文片段】")
    if text:
        snippet = text[:400].replace("\u3000", "  ")
        for line in snippet.split("\n"):
            if line.strip():
                print(f"  {line.strip()[:80]}")
    print(f"{'─'*60}")


def set_negotiation(conn, ch, sc, is_nego: bool, tags: list):
    conn.execute("""
        UPDATE scene_framework_cards
        SET is_negotiation_scene=?, negotiation_pattern_tags=?
        WHERE chapter_number=? AND scene_number=?
    """, (1 if is_nego else 0, json.dumps(tags, ensure_ascii=False), ch, sc))
    conn.commit()
    verdict = "✅ 確認談判" if is_nego else "❌ 移除談判標記"
    print(f"  → {verdict}，tags={tags}")


def cmd_list():
    conn = get_conn()
    rows = list_negotiation(conn)
    conn.close()
    if not rows:
        print("\n目前沒有標記為談判的場景（資料可能還在跑）")
        return
    print(f"\n共 {len(rows)} 個候選談判場景：\n")
    for row in rows:
        ch, sc, focal, conf, mst, tags_raw, *_ = row
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except Exception:
            tags = []
        print(f"  ch{ch:>2} s{sc} | {focal:<6} | {', '.join(tags[:2]) or '（無標籤）'}")


def cmd_review():
    conn = get_conn()
    rows = list_negotiation(conn)

    if not rows:
        print("\n沒有待審查的談判場景。等批次分析完成後再試。")
        conn.close()
        return

    print(f"\n共 {len(rows)} 個候選談判場景，逐一審查。")
    print("操作：y=確認談判  n=移除  s=跳過  f=看完整分析  q=退出\n")

    for row in rows:
        ch, sc = row[0], row[1]
        print_scene_brief(row)

        while True:
            cmd = input("  判斷 [y/n/s/f/q]? ").strip().lower()
            if cmd == "q":
                conn.close()
                print("\n審查中止。")
                return
            elif cmd == "s":
                print("  ⏭ 跳過")
                break
            elif cmd == "f":
                print_scene_full(ch, sc, conn)
            elif cmd == "y":
                # 確認為談判，可修改標籤
                cur_tags_raw = row[5]
                try:
                    cur_tags = json.loads(cur_tags_raw) if cur_tags_raw else []
                except Exception:
                    cur_tags = []
                print(f"  目前標籤：{cur_tags}")
                print(f"  可選標籤：{', '.join(ALL_TAGS)}")
                new_input = input("  修改標籤（直接 Enter 保留）：").strip()
                if new_input:
                    new_tags = [t.strip() for t in new_input.split(",") if t.strip() in ALL_TAGS]
                else:
                    new_tags = cur_tags
                set_negotiation(conn, ch, sc, True, new_tags)
                break
            elif cmd == "n":
                set_negotiation(conn, ch, sc, False, [])
                break
            else:
                print("  輸入 y / n / s / f / q")

    conn.close()
    print("\n✅ 審查完成")


def cmd_fix(ref: str):
    import re
    m = re.match(r"ch(\d+)s(\d+)", ref.lower())
    if not m:
        print("格式錯誤，請用 ch3s2")
        return
    ch, sc = int(m.group(1)), int(m.group(2))
    conn = get_conn()
    print_scene_full(ch, sc, conn)
    print(f"\n可選標籤：{', '.join(ALL_TAGS)}")
    is_nego = input("是談判場景？[y/n] ").strip().lower() == "y"
    if is_nego:
        tags_input = input("標籤（逗號分隔）：").strip()
        tags = [t.strip() for t in tags_input.split(",") if t.strip() in ALL_TAGS]
    else:
        tags = []
    set_negotiation(conn, ch, sc, is_nego, tags)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="談判場景人工審查")
    parser.add_argument("--list", action="store_true", help="只列表，不進入審查")
    parser.add_argument("--fix", metavar="chNsM", help="手動修正特定場景，如 ch3s2")
    args = parser.parse_args()

    if args.list:
        cmd_list()
    elif args.fix:
        cmd_fix(args.fix)
    else:
        cmd_review()

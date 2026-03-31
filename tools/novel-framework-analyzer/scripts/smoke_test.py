#!/usr/bin/env python3
"""
smoke_test.py — 全自動驗證腳本
對應 docs/dev-plan.md 第三章 TDD 驗證閘門

用法：
  python3 scripts/smoke_test.py
  python3 scripts/smoke_test.py --only B1 B2 F1
"""
import sys
import json
import urllib.request
import urllib.parse
import sqlite3
import argparse
from pathlib import Path

BASE = "http://localhost:8765"
DB_PATH = Path(__file__).parent.parent / "novel_analyzer.db"

PASS = "\033[32m PASS\033[0m"
FAIL = "\033[31m FAIL\033[0m"
SKIP = "\033[33m SKIP\033[0m"

def get(path: str) -> dict | list:
    url = BASE + path
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())

def check(label: str, cond: bool, detail: str = ""):
    status = PASS if cond else FAIL
    print(f"  {status}  {label}" + (f"  [{detail}]" if detail else ""))
    return cond

# ────────────────────────────────────────────────
# B1：談判場景篩選
# ────────────────────────────────────────────────
def test_b1():
    print("\n[B1] 談判場景篩選")
    results = []

    # ① API 回傳談判場景（含角色篩選）
    try:
        char = urllib.parse.quote("寧凡")
        data = get(f"/api/negotiation?focal_character={char}&book_id=shangchengzhixia-001")
        count = len(data)
        results.append(check("API: focal_character=寧凡 回傳 > 0 筆", count > 0, f"{count} 筆"))
    except Exception as e:
        results.append(check("API: 談判場景 endpoint 可達", False, str(e)))

    # ② 無 book_id 全書查詢
    try:
        char = urllib.parse.quote("寧凡")
        data = get(f"/api/negotiation?focal_character={char}")
        results.append(check("API: 不帶 book_id 全書查詢成功", len(data) >= 0, f"{len(data)} 筆"))
    except Exception as e:
        results.append(check("API: 不帶 book_id 全書查詢", False, str(e)))

    # ③ DB 直查確認資料完整
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE focal_character='寧凡' AND is_negotiation_scene=1"
        ).fetchone()
        conn.close()
        db_count = row[0]
        results.append(check("DB: 寧凡談判場景筆數 > 0", db_count > 0, f"DB={db_count}"))
    except Exception as e:
        results.append(check("DB: 查詢失敗", False, str(e)))

    return all(results)


# ────────────────────────────────────────────────
# B2：場景 Modal 全模式可點
# ────────────────────────────────────────────────
def test_b2():
    print("\n[B2] 場景 Modal — /api/scene 不帶 book_id")
    results = []

    # ① 不帶 book_id 查第一個章節場景
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT chapter_number, scene_number FROM scene_framework_cards LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            ch, sc = row
            data = get(f"/api/scene/{ch}/{sc}")
            results.append(check(f"API: /api/scene/{ch}/{sc}（無 book_id）回傳正常", "focal_character" in data))
        else:
            results.append(check("DB: 有場景資料", False, "DB 空"))
    except Exception as e:
        results.append(check("API: /api/scene 不帶 book_id", False, str(e)))

    # ② 帶 book_id 仍正常（book 模式）
    try:
        data = get("/api/scene/1/1?book_id=shangchengzhixia-001")
        results.append(check("API: /api/scene/1/1?book_id=... 正常", "focal_character" in data))
    except Exception as e:
        results.append(check("API: 帶 book_id 查詢", False, str(e)))

    return all(results)


# ────────────────────────────────────────────────
# B3：situation 欄位
# ────────────────────────────────────────────────
def test_b3():
    print("\n[B3] situation 欄位存在且非 null")
    results = []

    try:
        data = get("/api/scenes?limit=3&book_id=shangchengzhixia-001")
        items = data.get("items", [])
        if not items:
            results.append(check("API: /api/scenes 有資料", False, "0 筆"))
            return False

        has_field = "situation" in items[0]
        results.append(check("API: items[0] 含 situation 欄位", has_field))

        non_null = sum(1 for i in items if i.get("situation") is not None)
        results.append(check(f"API: {len(items)} 筆中至少 1 筆 situation 非 null", non_null > 0, f"{non_null}/{len(items)}"))

        # DB 直查
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT situation FROM scene_framework_cards WHERE book_id='shangchengzhixia-001' AND situation IS NOT NULL LIMIT 1"
        ).fetchone()
        conn.close()
        results.append(check("DB: situation 欄位有值", row is not None))
    except Exception as e:
        results.append(check("API: /api/scenes situation 欄位", False, str(e)))

    return all(results)


# ────────────────────────────────────────────────
# F1：角色清單 API（下拉選單依賴）
# ────────────────────────────────────────────────
def test_f1():
    print("\n[F1] 角色清單 API（弧線下拉選單依賴）")
    results = []

    try:
        data = get("/api/characters?book_id=shangchengzhixia-001")
        chars = data.get("characters", [])
        results.append(check("API: /api/characters 回傳非空", len(chars) > 0, f"{len(chars)} 個角色"))

        # 常見主角應存在
        for name in ["寧凡"]:
            results.append(check(f"API: {name} 在角色清單中", name in chars))

        # 不應包含垃圾值
        garbage = [c for c in chars if "未明確" in c or len(c) > 10]
        results.append(check("API: 角色清單無垃圾值", len(garbage) == 0, f"垃圾: {garbage[:3]}"))
    except Exception as e:
        results.append(check("API: /api/characters", False, str(e)))

    # 弧線 API 正常
    try:
        char = urllib.parse.quote("寧凡")
        data = get(f"/api/arc/{char}?book_id=shangchengzhixia-001")
        results.append(check("API: /api/arc/寧凡 回傳非空", len(data) > 0, f"{len(data)} 點"))
        if data:
            point = data[0]
            required = ["chapter_number", "scene_number", "mind_shift_type", "shift_score"]
            for field in required:
                results.append(check(f"API arc: 含欄位 {field}", field in point))
    except Exception as e:
        results.append(check("API: /api/arc/{character}", False, str(e)))

    return all(results)


# ────────────────────────────────────────────────
# F2：簡繁轉換（opencc 可用性）
# ────────────────────────────────────────────────
def test_f2():
    print("\n[F2] 簡繁轉換（opencc）")
    results = []

    try:
        import opencc
        c = opencc.OpenCC("s2twp")
        test_in = "联系员在这里讨论"
        out = c.convert(test_in)
        has_trad = any(ch in out for ch in ["聯", "這", "裡", "討"])
        results.append(check("opencc: s2twp 轉換成功", has_trad, f"{test_in} → {out}"))
    except ImportError:
        results.append(check("opencc: 模組已安裝", False, "pip3 install opencc-python-reimplemented"))
    except Exception as e:
        results.append(check("opencc: 轉換執行", False, str(e)))

    return all(results)


# ────────────────────────────────────────────────
# 主程式
# ────────────────────────────────────────────────
TESTS = {
    "B1": ("談判場景篩選", test_b1),
    "B2": ("場景 Modal 全模式", test_b2),
    "B3": ("situation 欄位", test_b3),
    "F1": ("角色清單（弧線依賴）", test_f1),
    "F2": ("簡繁轉換", test_f2),
}

def main():
    parser = argparse.ArgumentParser(description="Novel Analyzer Smoke Tests")
    parser.add_argument("--only", nargs="*", help="只跑指定 test id，例如 B1 B2")
    args = parser.parse_args()

    # 確認 server 可達
    try:
        get("/api/books")
        print(f"✓ Server 已運行：{BASE}")
    except Exception:
        print(f"✗ Server 無法連線：{BASE}  → 請先執行 python3 server.py")
        sys.exit(1)

    run_ids = args.only if args.only else list(TESTS.keys())
    passed, failed = [], []

    for tid in run_ids:
        if tid not in TESTS:
            print(f"[SKIP] 未知 test id: {tid}")
            continue
        name, fn = TESTS[tid]
        ok = fn()
        (passed if ok else failed).append(f"{tid}:{name}")

    print("\n" + "─" * 48)
    print(f"結果  通過 {len(passed)}/{len(passed)+len(failed)}")
    if failed:
        print(f"未通過: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("全部通過 ✓")

if __name__ == "__main__":
    main()

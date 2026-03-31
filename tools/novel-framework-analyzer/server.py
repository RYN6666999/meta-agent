"""
server.py — 局心欲變分析系統 Web 介面
執行：python3 server.py
開啟：http://localhost:8765
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

app = FastAPI(title="局心欲變分析系統")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH      = ROOT / "novel_analyzer.db"
UPLOAD_DIR   = ROOT / "uploads"
BOOK_REGISTRY_PATH = ROOT / "book_registry.json"
UPLOAD_DIR.mkdir(exist_ok=True)

# 進度暫存（記憶體，重啟清空）
_jobs: dict[str, dict] = {}


# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def json_safe(val):
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return val
    return val


def load_book_registry() -> dict:
    if not BOOK_REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(BOOK_REGISTRY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_book_registry(registry: dict):
    BOOK_REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_analysis_job(filepath: str, chapters_start: int, chapters_end: int, mode: str, book_id: str):
    job_id = uuid.uuid4().hex[:10]
    _jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "log": [],
        "book_id": book_id,
        "chapters_start": chapters_start,
        "chapters_end": chapters_end,
    }

    async def run_job():
        cmd = [
            sys.executable, str(ROOT / "scripts" / "batch_analyze.py"),
            "--chapters", f"{chapters_start}-{chapters_end}",
            "--mode", mode,
            "--skip-existing",
        ]
        env = os.environ.copy()
        env["NOVEL_PATH_OVERRIDE"] = filepath
        env["BOOK_ID_OVERRIDE"] = book_id

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
            env=env,
        )
        async for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").rstrip()
            _jobs[job_id]["log"].append(text)
            if "✅" in text or "🟢" in text:
                _jobs[job_id]["progress"] += 1
            if "場景：" in text and "個" in text:
                import re
                m = re.search(r"場景：(\d+)", text)
                if m:
                    _jobs[job_id]["total"] = int(m.group(1))
        await proc.wait()
        _jobs[job_id]["status"] = "done" if proc.returncode == 0 else "error"

    asyncio.create_task(run_job())
    return job_id


# ─────────────────────────────────────────────
# API routes
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# 定價表（USD per 1M tokens）
# ─────────────────────────────────────────────
PRICING = {
    "openrouter/anthropic/claude-haiku-4-5": {"input": 0.80, "output": 4.00, "label": "Haiku 4.5"},
    "openrouter/anthropic/claude-3-haiku":   {"input": 0.25, "output": 1.25, "label": "Haiku 3"},
    "openrouter/anthropic/claude-sonnet-4-5":{"input": 3.00, "output": 15.0, "label": "Sonnet 4.5"},
    "openrouter/anthropic/claude-opus-4":    {"input": 15.0, "output": 75.0, "label": "Opus 4"},
    # 對照組（如果以 Sonnet / Opus 跑，費用會是多少）
    "_compare_sonnet": {"input": 3.00, "output": 15.0, "label": "Sonnet 4.5（對照）"},
    "_compare_opus":   {"input": 15.0, "output": 75.0, "label": "Opus 4（對照）"},
}
PROMPT_OVERHEAD_TOKENS = 1_600  # 固定 system + user 模板 overhead

def _estimate_tokens(scene_text_len: int, resp_len: int):
    """
    估算 token 數：
    - input = prompt overhead + scene_text（中文 ~1.5 char/token）
    - output = raw_llm_response（中文 JSON 混合 ~2.0 char/token）
    """
    input_tok  = PROMPT_OVERHEAD_TOKENS + int(scene_text_len / 1.5)
    output_tok = int(resp_len / 2.0) if resp_len else 800  # 無回應時估 800 output
    return input_tok, output_tok

def _calc_cost(input_tok: int, output_tok: int, model: str) -> float:
    p = PRICING.get(model, {"input": 0.80, "output": 4.00})
    return (input_tok * p["input"] + output_tok * p["output"]) / 1_000_000


@app.get("/api/costs")
def api_costs(book_id: Optional[str] = None):
    """成本分析：依章節、日期、模型估算 token 與 USD 費用"""
    conn = get_db()
    params = []
    where_sql = ""
    if book_id:
        where_sql = "WHERE book_id = ?"
        params.append(book_id)

    rows = conn.execute(f"""
        SELECT chapter_number, scene_number, model_used,
               LENGTH(scene_text)        AS text_len,
               LENGTH(raw_llm_response)  AS resp_len,
               created_at
        FROM scene_framework_cards
        {where_sql}
        ORDER BY chapter_number, scene_number
    """, params).fetchall()

    scenes = []
    by_chapter: dict[int, dict] = {}
    by_model: dict[str, dict]   = {}
    total_input = total_output  = 0
    total_cost  = 0.0

    for r in rows:
        ch, sc, model, text_len, resp_len, _created_at = r
        inp, out = _estimate_tokens(text_len or 0, resp_len or 0)
        cost = _calc_cost(inp, out, model)

        total_input  += inp
        total_output += out
        total_cost   += cost

        scenes.append({
            "chapter_number": ch, "scene_number": sc,
            "model": model,
            "input_tokens": inp, "output_tokens": out,
            "total_tokens": inp + out,
            "cost_usd": round(cost, 6),
        })

        # 按章節彙總
        if ch not in by_chapter:
            by_chapter[ch] = {"chapter": ch, "scenes": 0, "tokens": 0, "cost_usd": 0.0}
        by_chapter[ch]["scenes"] += 1
        by_chapter[ch]["tokens"] += inp + out
        by_chapter[ch]["cost_usd"] = round(by_chapter[ch]["cost_usd"] + cost, 6)

        # 按模型彙總
        if model not in by_model:
            label = PRICING.get(model, {}).get("label", model)
            by_model[model] = {"model": model, "label": label, "scenes": 0,
                                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        by_model[model]["scenes"]       += 1
        by_model[model]["input_tokens"] += inp
        by_model[model]["output_tokens"]+= out
        by_model[model]["cost_usd"]      = round(by_model[model]["cost_usd"] + cost, 6)

    # 對照試算（Smart 路由、Sonnet、Opus）
    # Smart 路由：寧凡場景數 × Haiku 費率 + 其他角色 × 0
    if book_id:
        smart_haiku_scenes = conn.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE focal_character=? AND book_id=?",
            ("寧凡", book_id),
        ).fetchone()[0]
    else:
        smart_haiku_scenes = conn.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE focal_character=?",
            ("寧凡",),
        ).fetchone()[0]
    smart_ratio = smart_haiku_scenes / len(scenes) if scenes else 0
    smart_cost  = round(total_cost * smart_ratio, 4)

    compare = [{"label": "Smart 路由（寧凡→Haiku，其他→Free）",
                "cost_usd": smart_cost,
                "savings_pct": round((1 - smart_cost / total_cost) * 100, 1) if total_cost else 0}]
    for key in ("_compare_sonnet", "_compare_opus"):
        p = PRICING[key]
        c = (total_input * p["input"] + total_output * p["output"]) / 1_000_000
        compare.append({"label": p["label"], "cost_usd": round(c, 4), "savings_pct": None})

    conn.close()

    return {
        "total_scenes":        len(scenes),
        "total_input_tokens":  total_input,
        "total_output_tokens": total_output,
        "total_tokens":        total_input + total_output,
        "total_cost_usd":      round(total_cost, 4),
        "avg_cost_per_scene":  round(total_cost / len(scenes), 6) if scenes else 0,
        "by_chapter":          sorted(by_chapter.values(), key=lambda x: x["chapter"]),
        "by_model":            list(by_model.values()),
        "compare_models":      compare,
        "scenes":              scenes,
    }


@app.get("/api/dashboard")
def api_dashboard():
    """總覽 — 全書聚合資料、書籍進度、資料品質警示、跨書分布"""
    registry = load_book_registry()
    conn = get_db()
    cur  = conn.cursor()

    # ── 1. 全域數字（只算信心 >= 0.6 的有效場景）
    total_all   = cur.execute("SELECT COUNT(*) FROM scene_framework_cards").fetchone()[0]
    total_clean = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE confidence_score >= 0.6").fetchone()[0]
    nego_clean  = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE is_negotiation_scene=1 AND confidence_score >= 0.6").fetchone()[0]
    decision_clean = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE scene_labels LIKE '%decision%' AND confidence_score >= 0.6").fetchone()[0]
    unique_chars = cur.execute("SELECT COUNT(DISTINCT focal_character) FROM scene_framework_cards WHERE confidence_score >= 0.6").fetchone()[0]
    avg_conf_all = cur.execute("SELECT AVG(confidence_score) FROM scene_framework_cards").fetchone()[0] or 0

    # ── 2. 每本書進度 + 品質指標
    books_raw = cur.execute("""
        SELECT book_id,
               COUNT(*) total,
               SUM(CASE WHEN confidence_score >= 0.6 THEN 1 ELSE 0 END) clean,
               SUM(CASE WHEN confidence_score < 0.45 THEN 1 ELSE 0 END) low_conf,
               AVG(confidence_score) avg_conf,
               MAX(chapter_number) max_ch,
               SUM(CASE WHEN is_negotiation_scene=1 THEN 1 ELSE 0 END) nego
        FROM scene_framework_cards
        GROUP BY book_id
    """).fetchall()

    # 垃圾角色名偵測：複用 _is_valid_character() 篩選，Python 層統一規則
    all_chars_rows = cur.execute("""
        SELECT book_id, focal_character, COUNT(*) n
        FROM scene_framework_cards
        GROUP BY book_id, focal_character
    """).fetchall()
    garbage_by_book: dict = {}
    for r in all_chars_rows:
        if not _is_valid_character(r["focal_character"]):
            bid = r["book_id"]
            garbage_by_book.setdefault(bid, []).append({"name": r["focal_character"], "count": r["n"]})

    books_list = []
    for r in books_raw:
        bid   = r["book_id"]
        meta  = registry.get(bid, {})
        detected = int(meta.get("detected_chapters") or 0)
        garbage  = garbage_by_book.get(bid, [])
        books_list.append({
            "book_id":      bid,
            "display_name": meta.get("display_name") or bid,
            "book_type":    meta.get("book_type") or "",
            "tags":         meta.get("tags") or [],
            "total":        int(r["total"]),
            "clean":        int(r["clean"]),
            "low_conf":     int(r["low_conf"]),
            "avg_conf":     round(float(r["avg_conf"] or 0), 3),
            "max_ch":       int(r["max_ch"] or 0),
            "detected_ch":  detected,
            "nego":         int(r["nego"]),
            "garbage_chars": garbage,
            "garbage_count": sum(g["count"] for g in garbage),
        })

    # ── 3. 跨書轉變類型分布（只算高品質資料）
    shifts_clean = cur.execute("""
        SELECT mind_shift_type t, COUNT(*) n FROM scene_framework_cards
        WHERE confidence_score >= 0.6
        GROUP BY mind_shift_type ORDER BY n DESC
    """).fetchall()

    # ── 4. 高價值場景（conf>=0.8 且談判，Top 5）
    top_scenes = cur.execute("""
        SELECT book_id, chapter_number, scene_number, focal_character,
               confidence_score, mind_shift_type, mind_shift_intensity
        FROM scene_framework_cards
        WHERE confidence_score >= 0.8 AND is_negotiation_scene=1
        ORDER BY confidence_score DESC, mind_shift_intensity DESC
        LIMIT 5
    """).fetchall()

    conn.close()
    return {
        "global": {
            "total_all":      total_all,
            "total_clean":    total_clean,
            "nego_clean":     nego_clean,
            "decision_clean": decision_clean,
            "unique_chars":   unique_chars,
            "avg_conf":       round(avg_conf_all, 3),
        },
        "books":       books_list,
        "shift_dist":  [{"type": r["t"], "count": r["n"]} for r in shifts_clean],
        "top_scenes":  [dict(r) for r in top_scenes],
    }


@app.delete("/api/book/{book_id}/garbage")
def api_clean_garbage(book_id: str):
    """清理指定書籍的垃圾角色名場景"""
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        DELETE FROM scene_framework_cards
        WHERE book_id=? AND (
            focal_character IN ('未知','法則','條件','因素','環境','機制','原則','現象','系統',
                '理論','結果','影響','效果','過程','方式','方法','模式','關係','結構',
                '框架','背景','情況','狀態','階段','程度','問題','答案','原因',
                '有人','沒有','所有','任何','這個','那個','一個','每個',
                '同烟','得到','找到','看到','想到','讓人','使人','令人','還有',
                '也有','只有','件中','其中','之中','心中','自己','他們','我們',
                '联系员','还有人','让人','自己的轨','得到的回')
            OR length(focal_character) > 10
            OR focal_character GLOB '*的*'
            OR focal_character GLOB '*了*'
        )
    """, (book_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"ok": True, "deleted": deleted}


@app.get("/api/summary")
def api_summary(book_id: Optional[str] = None):
    conn = get_db()
    cur = conn.cursor()
    if book_id:
        total = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE book_id=?", (book_id,)).fetchone()[0]
        nego = cur.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE is_negotiation_scene=1 AND book_id=?",
            (book_id,),
        ).fetchone()[0]
        decisions = cur.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE scene_labels LIKE '%decision%' AND book_id=?",
            (book_id,),
        ).fetchone()[0]
        max_ch = cur.execute("SELECT MAX(chapter_number) FROM scene_framework_cards WHERE book_id=?", (book_id,)).fetchone()[0] or 0
        avg_conf = cur.execute("SELECT AVG(confidence_score) FROM scene_framework_cards WHERE book_id=?", (book_id,)).fetchone()[0] or 0
        chars = cur.execute("""
            SELECT focal_character, COUNT(*) n FROM scene_framework_cards
            WHERE book_id=?
            GROUP BY focal_character ORDER BY n DESC LIMIT 6
        """, (book_id,)).fetchall()
        shifts = cur.execute("""
            SELECT mind_shift_type, COUNT(*) n FROM scene_framework_cards
            WHERE book_id=?
            GROUP BY mind_shift_type ORDER BY n DESC
        """, (book_id,)).fetchall()
    else:
        total = cur.execute("SELECT COUNT(*) FROM scene_framework_cards").fetchone()[0]
        nego = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE is_negotiation_scene=1").fetchone()[0]
        decisions = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE scene_labels LIKE '%decision%'").fetchone()[0]
        max_ch = cur.execute("SELECT MAX(chapter_number) FROM scene_framework_cards").fetchone()[0] or 0
        avg_conf = cur.execute("SELECT AVG(confidence_score) FROM scene_framework_cards").fetchone()[0] or 0
        chars = cur.execute("""
            SELECT focal_character, COUNT(*) n FROM scene_framework_cards
            GROUP BY focal_character ORDER BY n DESC LIMIT 6
        """).fetchall()
        shifts = cur.execute("""
            SELECT mind_shift_type, COUNT(*) n FROM scene_framework_cards
            GROUP BY mind_shift_type ORDER BY n DESC
        """).fetchall()

    conn.close()
    return {
        "total_scenes": total,
        "negotiation_scenes": nego,
        "decision_scenes": decisions,
        "chapters_analyzed": max_ch,
        "avg_confidence": round(avg_conf, 3),
        "top_characters": [{"name": r[0], "count": r[1]} for r in chars],
        "shift_distribution": [{"type": r[0], "count": r[1]} for r in shifts],
    }


@app.get("/api/progress/books")
def api_progress_books():
    """多書籍進度：按書籍分離的進度統計"""
    conn = get_db()

    # 讀進度 log
    books = conn.execute("""
        SELECT book_id, chapter_analyzed, total_chapters
        FROM progress_log
        ORDER BY last_updated DESC
    """).fetchall()

    result = []
    for book_id, ch_analyzed, total_ch in books:
        # 如果進度 log 沒有 total_chapters，則重新計算
        if not total_ch:
            total_ch = conn.execute(
                "SELECT MAX(chapter_number) FROM scene_framework_cards WHERE book_id=?",
                (book_id,)
            ).fetchone()[0] or 0

        scenes_count = conn.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE book_id=?",
            (book_id,)
        ).fetchone()[0]

        nego_count = conn.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE book_id=? AND is_negotiation_scene=1",
            (book_id,)
        ).fetchone()[0]

        decision_count = conn.execute(
            "SELECT COUNT(*) FROM scene_framework_cards WHERE book_id=? AND scene_labels LIKE '%decision%'",
            (book_id,)
        ).fetchone()[0]

        result.append({
            "book_id": book_id,
            "chapter_analyzed": ch_analyzed,
            "total_chapters": total_ch,
            "progress_pct": round(ch_analyzed / total_ch * 100, 1) if total_ch > 0 else 0,
            "total_scenes": scenes_count,
            "negotiation_scenes": nego_count,
            "decision_scenes": decision_count,
        })

    conn.close()
    return result


@app.get("/api/progress")
def api_progress(book_id: Optional[str] = None):
    """逐章進度：每章的場景數、信心分數、決策/談判數，用於視覺化進度牆。
    book_id 指定時只顯示該書；否則顯示全部書籍合併進度。
    total_chapters 從 book_registry 讀取 detected_chapters；全局模式取最大值。
    """
    conn = get_db()

    where = "WHERE book_id=?" if book_id else ""
    params = (book_id,) if book_id else ()

    rows = conn.execute(f"""
        SELECT chapter_number,
               COUNT(*)                                                      AS scenes,
               ROUND(AVG(confidence_score), 3)                               AS avg_conf,
               COUNT(CASE WHEN scene_labels LIKE '%decision%' THEN 1 END)    AS decisions,
               COUNT(CASE WHEN is_negotiation_scene=1 THEN 1 END)            AS negotiation,
               MAX(match_level)                                               AS best_match,
               GROUP_CONCAT(DISTINCT focal_character)                        AS characters
        FROM scene_framework_cards
        {where}
        GROUP BY chapter_number
        ORDER BY chapter_number
    """, params).fetchall()
    conn.close()

    # 計算 total_chapters：優先用 registry 的 detected_chapters，否則用已分析最大章號
    registry = load_book_registry()
    if book_id:
        meta = registry.get(book_id, {})
        detected = int(meta.get("detected_chapters") or 0)
        max_analyzed = rows[-1][0] if rows else 0
        total_chapters = max(detected, max_analyzed, 1)
    else:
        # 全局：各書 detected_chapters 加總，或取最大已分析章號（上城之下等舊書）
        detected_sum = sum(int(m.get("detected_chapters") or 0) for m in registry.values())
        max_analyzed = rows[-1][0] if rows else 0
        total_chapters = max(detected_sum, max_analyzed, 1)

    analyzed = {r[0]: {
        "chapter": r[0], "scenes": r[1], "avg_conf": r[2],
        "decisions": r[3], "negotiation": r[4],
        "best_match": r[5], "characters": r[6] or ""
    } for r in rows}

    chapters = []
    for ch in range(1, total_chapters + 1):
        if ch in analyzed:
            chapters.append({"chapter": ch, "status": "done", **analyzed[ch]})
        else:
            chapters.append({"chapter": ch, "status": "pending",
                             "scenes": 0, "avg_conf": 0, "decisions": 0,
                             "negotiation": 0, "best_match": None, "characters": ""})

    done = len(analyzed)
    return {
        "total_chapters": total_chapters,
        "done_chapters": done,
        "pending_chapters": max(total_chapters - done, 0),
        "progress_pct": round(done / total_chapters * 100, 2),
        "chapters": chapters,
    }


@app.get("/api/books")
def api_books():
    registry = load_book_registry()
    conn = get_db()
    rows = conn.execute("""
        SELECT book_id,
               COUNT(*) AS scene_count,
               MAX(chapter_number) AS max_chapter,
               MAX(created_at) AS last_analyzed_at
        FROM scene_framework_cards
        GROUP BY book_id
        ORDER BY last_analyzed_at DESC
    """).fetchall()
    conn.close()

    items = []
    known = set()
    for r in rows:
        row_book_id = r["book_id"]
        meta = registry.get(row_book_id, {})
        detected = int(meta.get("detected_chapters") or 0)
        max_ch = int(r["max_chapter"] or 0)
        items.append({
            "book_id": row_book_id,
            "display_name": meta.get("display_name") or row_book_id,
            "filename": meta.get("filename"),
            "path": meta.get("path"),
            "detected_chapters": detected,
            "analyzed_scenes": int(r["scene_count"] or 0),
            "max_analyzed_chapter": max_ch,
            "next_chapter": max_ch + 1,
            "is_completed": bool(detected and max_ch >= detected),
            "uploaded_at": meta.get("uploaded_at"),
            "last_analyzed_at": r["last_analyzed_at"],
            # 書架擴充欄位
            "book_type": meta.get("book_type", ""),
            "notes": meta.get("notes", ""),
            "tags": meta.get("tags", []),
        })
        known.add(row_book_id)

    for row_book_id, meta in registry.items():
        if row_book_id in known:
            continue
        detected = int(meta.get("detected_chapters") or 0)
        items.append({
            "book_id": row_book_id,
            "display_name": meta.get("display_name") or row_book_id,
            "filename": meta.get("filename"),
            "path": meta.get("path"),
            "detected_chapters": detected,
            "analyzed_scenes": 0,
            "max_analyzed_chapter": 0,
            "next_chapter": 1,
            "is_completed": False,
            "uploaded_at": meta.get("uploaded_at"),
            "last_analyzed_at": None,
            "book_type": meta.get("book_type", ""),
            "notes": meta.get("notes", ""),
            "tags": meta.get("tags", []),
        })

    return {"items": items}


@app.get("/api/scenes")
def api_scenes(
    chapter: Optional[int] = None,
    char: Optional[str] = None,
    match: Optional[str] = None,
    negotiation: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    book_id: Optional[str] = None,
):
    conn = get_db()
    cur = conn.cursor()
    where, params = [], []
    if chapter is not None:
        where.append("chapter_number=?"); params.append(chapter)
    if char:
        where.append("(focal_character=? OR secondary_characters LIKE ?)"); params += [char, f"%{char}%"]
    if match:
        where.append("match_level=?"); params.append(match)
    if negotiation is not None:
        where.append("is_negotiation_scene=?"); params.append(1 if negotiation else 0)
    if book_id:
        where.append("book_id=?"); params.append(book_id)
    sql = "SELECT chapter_number, scene_number, focal_character, secondary_characters, match_level, confidence_score, mind_shift_type, mind_shift_intensity, is_negotiation_scene, negotiation_pattern_tags, created_at, book_id, situation, SUBSTR(scene_text,1,120) as scene_text_preview FROM scene_framework_cards"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY chapter_number, scene_number LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = cur.execute(sql, params).fetchall()
    total = cur.execute(
        "SELECT COUNT(*) FROM scene_framework_cards" + (" WHERE " + " AND ".join(where) if where else ""),
        params[:-2],
    ).fetchone()[0]
    conn.close()
    return {
        "total": total,
        "items": [dict(r) for r in rows],
    }


@app.get("/api/scene/{chapter}/{scene}")
def api_scene_detail(chapter: int, scene: int, book_id: Optional[str] = None):
    conn = get_db()
    cur = conn.cursor()
    if book_id:
        row = cur.execute("""
            SELECT * FROM scene_framework_cards
            WHERE chapter_number=? AND scene_number=? AND book_id=? LIMIT 1
        """, (chapter, scene, book_id)).fetchone()
    else:
        row = cur.execute("""
            SELECT * FROM scene_framework_cards
            WHERE chapter_number=? AND scene_number=? LIMIT 1
        """, (chapter, scene)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "場景不存在")
    d = dict(row)
    for key in ("situation", "desire", "mind_shift", "judgment", "secondary_characters", "negotiation_pattern_tags"):
        d[key] = json_safe(d.get(key))
    return d


@app.patch("/api/scene/{chapter}/{scene}/focal_character")
def api_patch_focal_character(
    chapter: int, scene: int,
    body: dict,
    book_id: Optional[str] = None,
):
    """手動更正場景的 focal_character 名稱（雙向聯動用）"""
    new_name = (body.get("focal_character") or "").strip()
    if not new_name:
        raise HTTPException(400, "focal_character 不可為空")
    conn = get_db()
    if book_id:
        conn.execute(
            "UPDATE scene_framework_cards SET focal_character=? WHERE chapter_number=? AND scene_number=? AND book_id=?",
            (new_name, chapter, scene, book_id)
        )
    else:
        conn.execute(
            "UPDATE scene_framework_cards SET focal_character=? WHERE chapter_number=? AND scene_number=?",
            (new_name, chapter, scene)
        )
    conn.commit()
    conn.close()
    return {"ok": True, "focal_character": new_name}


@app.patch("/api/scene/{chapter}/{scene}/annotate")
def api_annotate_scene(
    chapter: int, scene: int,
    body: dict,
    book_id: Optional[str] = None,
):
    """
    人工標注 API — 儲存修正值並記錄 AI 原值 diff。
    body 可含任意組合：
      reviewer_notes, human_focal_character, human_match_level,
      human_shift_type, human_shift_intensity,
      is_golden_example (bool), is_human_reviewed (bool)
    """
    import json as _json
    from datetime import datetime, timezone

    conn = get_db()
    where = "chapter_number=? AND scene_number=?"
    params_sel = [chapter, scene]
    if book_id:
        where += " AND book_id=?"
        params_sel.append(book_id)

    row = conn.execute(
        f"SELECT * FROM scene_framework_cards WHERE {where} LIMIT 1", params_sel
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "場景不存在")

    original = dict(row)

    # 收集需要更新的欄位
    updates: dict = {}

    if "reviewer_notes" in body:
        updates["reviewer_notes"] = body["reviewer_notes"]
    if "human_focal_character" in body:
        hfc = (body["human_focal_character"] or "").strip()
        updates["human_focal_character"] = hfc
        # 同步更新主欄位（讓過濾邏輯立即生效）
        if hfc:
            updates["focal_character"] = hfc
    if "human_match_level" in body:
        updates["human_match_level"] = body["human_match_level"]
    if "human_shift_type" in body:
        updates["human_shift_type"] = body["human_shift_type"]
    if "human_shift_intensity" in body:
        updates["human_shift_intensity"] = body["human_shift_intensity"]
    if "is_golden_example" in body:
        updates["is_golden_example"] = 1 if body["is_golden_example"] else 0
    if "is_human_reviewed" in body:
        updates["is_human_reviewed"] = 1 if body["is_human_reviewed"] else 0

    # 記錄 AI 原值（只在第一次標注時快照）
    if not original.get("ai_original_values"):
        snapshot = {
            "focal_character": original.get("focal_character"),
            "match_level":     original.get("match_level"),
            "mind_shift_type": original.get("mind_shift_type"),
            "mind_shift_intensity": original.get("mind_shift_intensity"),
        }
        updates["ai_original_values"] = _json.dumps(snapshot, ensure_ascii=False)

    updates["human_annotated_at"] = datetime.now(timezone.utc).isoformat()

    set_clause = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + params_sel
    conn.execute(
        f"UPDATE scene_framework_cards SET {set_clause} WHERE {where}", vals
    )
    conn.commit()

    # 回傳 diff 摘要（方便前端顯示）
    ai_snap = _json.loads(updates.get("ai_original_values") or original.get("ai_original_values") or "{}")
    diff = {}
    for field in ("focal_character", "match_level", "mind_shift_type", "mind_shift_intensity"):
        human_key = f"human_{field}" if field != "focal_character" else "human_focal_character"
        h_val = updates.get(human_key) or body.get(human_key)
        if h_val is not None and str(h_val) != str(ai_snap.get(field, "")):
            diff[field] = {"ai": ai_snap.get(field), "human": h_val}
    conn.close()
    return {"ok": True, "diff": diff, "fields_updated": list(updates.keys())}


@app.get("/api/annotations/export")
def api_export_annotations(book_id: Optional[str] = None, golden_only: bool = False):
    """
    匯出人工標注資料 — 供 AI 學習用。
    回傳結構包含：AI 原值、人工修正值、diff、reviewer_notes
    golden_only=true → 只回傳標記為 golden example 的場景
    """
    import json as _json
    conn = get_db()
    where_parts = ["human_annotated_at IS NOT NULL"]
    params = []
    if book_id:
        where_parts.append("book_id=?")
        params.append(book_id)
    if golden_only:
        where_parts.append("is_golden_example=1")

    rows = conn.execute(
        f"""SELECT chapter_number, scene_number, book_id, focal_character,
                   match_level, mind_shift_type, mind_shift_intensity,
                   situation, desire, mind_shift,
                   reviewer_notes, human_focal_character, human_match_level,
                   human_shift_type, human_shift_intensity,
                   ai_original_values, is_golden_example, human_annotated_at
            FROM scene_framework_cards
            WHERE {' AND '.join(where_parts)}
            ORDER BY human_annotated_at DESC""",
        params
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        ai_orig = _json.loads(d.get("ai_original_values") or "{}")
        diff = {}
        for field in ("focal_character", "match_level", "mind_shift_type", "mind_shift_intensity"):
            h_key = "human_focal_character" if field == "focal_character" else f"human_{field}"
            h_val = d.get(h_key)
            if h_val is not None and str(h_val) != str(ai_orig.get(field, "")):
                diff[field] = {"ai": ai_orig.get(field), "human": h_val}
        for k in ("situation", "desire", "mind_shift"):
            d[k] = json_safe(d.get(k))
        d["diff_summary"] = diff
        d["has_diff"] = bool(diff)
        result.append(d)

    return {
        "total": len(result),
        "golden_count": sum(1 for r in result if r.get("is_golden_example")),
        "items": result,
    }


@app.get("/api/decisions")
def api_decisions(book_id: Optional[str] = None):
    """行動決策場景：scene_labels 含 'decision'"""
    conn = get_db()
    if book_id:
        rows = conn.execute("""
            SELECT chapter_number, scene_number, focal_character,
                   confidence_score, match_level, mind_shift_type, mind_shift_intensity,
                   scene_labels, situation, desire, mind_shift, scene_text, book_id
            FROM scene_framework_cards
            WHERE scene_labels LIKE '%decision%' AND book_id=?
            ORDER BY chapter_number, scene_number
        """, (book_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT chapter_number, scene_number, focal_character,
                   confidence_score, match_level, mind_shift_type, mind_shift_intensity,
                   scene_labels, situation, desire, mind_shift, scene_text, book_id
            FROM scene_framework_cards
            WHERE scene_labels LIKE '%decision%'
            ORDER BY chapter_number, scene_number
        """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if not _is_valid_character(d.get("focal_character") or ""):
            continue
        for k in ("scene_labels", "situation", "desire", "mind_shift"):
            d[k] = json_safe(d[k])
        d["scene_text_preview"] = (d.get("scene_text") or "")[:300]
        d.pop("scene_text", None)
        result.append(d)
    return result


@app.get("/api/negotiation")
def api_negotiation(book_id: Optional[str] = None, focal_character: Optional[str] = None):
    conn = get_db()
    where_parts = ["is_negotiation_scene=1"]
    params = []

    if book_id:
        where_parts.append("book_id=?")
        params.append(book_id)
    if focal_character:
        where_parts.append("focal_character=?")
        params.append(focal_character)

    where_clause = " AND ".join(where_parts)
    query = f"""
        SELECT chapter_number, scene_number, focal_character,
               confidence_score, mind_shift_type, match_level, negotiation_pattern_tags,
               situation, desire, mind_shift, scene_text, book_id
        FROM scene_framework_cards
        WHERE {where_clause}
        ORDER BY chapter_number, scene_number
    """

    rows = conn.execute(query, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for k in ("negotiation_pattern_tags", "situation", "desire", "mind_shift"):
            d[k] = json_safe(d[k])
        d["scene_text_preview"] = (d.get("scene_text") or "")[:300]
        d.pop("scene_text", None)
        result.append(d)
    return result



# 垃圾角色名關鍵字黑名單
_CHAR_GARBAGE_KEYWORDS = [
    "未明確", "指定", "敘述者", "讀者", "視角", "narrator", "旁白",
    "法则", "法則", "无人", "有人",
]

def _is_valid_character(name: str) -> bool:
    """判斷角色名是否為有效人名（非垃圾分析結果）"""
    if not name:
        return False
    # 方括號標記的描述性佔位符（如 [個別人物法則的傳播者]）直接排除
    if name.startswith("[") and name.endswith("]"):
        return False
    # 含間隔號（·）的非虛構人名最長可達 15 字（如「達內爾·"老板人"·麥吉」）
    has_middle_dot = "·" in name or "\u00b7" in name
    max_len = 15 if has_middle_dot else 8
    # 長度：1 字太短，超過上限通常是描述句
    if len(name) < 2 or len(name) > max_len:
        return False
    # 含空格或斜線通常是描述（敘述者/讀者視角）
    if "/" in name or "／" in name or " " in name or "　" in name:
        return False
    # 黑名單關鍵字
    for kw in _CHAR_GARBAGE_KEYWORDS:
        if kw in name:
            return False
    return True


@app.get("/api/characters")
def api_characters(book_id: Optional[str] = None):
    """返回此書籍或全局的所有角色清單（已過濾垃圾名）"""
    conn = get_db()
    if book_id:
        rows = conn.execute("""
            SELECT focal_character, COUNT(*) as cnt
            FROM scene_framework_cards
            WHERE book_id=?
            GROUP BY focal_character
            ORDER BY cnt DESC
        """, (book_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT focal_character, COUNT(*) as cnt
            FROM scene_framework_cards
            GROUP BY focal_character
            ORDER BY cnt DESC
        """).fetchall()
    conn.close()
    characters = [r[0] for r in rows if _is_valid_character(r[0])]
    return {"characters": characters}


@app.get("/api/arc/{character}")
def api_arc(character: str, book_id: Optional[str] = None):
    conn = get_db()
    if book_id:
        rows = conn.execute("""
            SELECT chapter_number, scene_number, mind_shift_type, mind_shift_intensity,
                   match_level, confidence_score, mind_shift, is_negotiation_scene, book_id
            FROM scene_framework_cards
            WHERE focal_character=? AND book_id=?
            ORDER BY chapter_number, scene_number
        """, (character, book_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT chapter_number, scene_number, mind_shift_type, mind_shift_intensity,
                   match_level, confidence_score, mind_shift, is_negotiation_scene, book_id
            FROM scene_framework_cards
            WHERE focal_character=?
            ORDER BY chapter_number, scene_number
        """, (character,)).fetchall()
    conn.close()
    type_score = {"none": 0, "emotion": 1, "stance": 2, "strategy": 3, "values": 4, "identity": 5}
    result = []
    for r in rows:
        d = dict(r)
        d["mind_shift"] = json_safe(d["mind_shift"])
        d["shift_score"] = type_score.get(d["mind_shift_type"] or "none", 0)
        result.append(d)
    return result


# ── Nonfiction 專屬端點 ──────────────────────────────────────────────────────

@app.get("/api/nonfiction/cases")
def api_nonfiction_cases(book_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    """返回 nonfiction_case 類型場景（真實案例）"""
    conn = get_db()
    where, params = ["scene_type='nonfiction_case'"], []
    if book_id:
        where.append("book_id=?"); params.append(book_id)
    sql = f"""
        SELECT chapter_number, scene_number, focal_character, confidence_score,
               match_level, situation, mind_shift, desire, book_id,
               SUBSTR(scene_text,1,200) as scene_text_preview
        FROM scene_framework_cards
        WHERE {' AND '.join(where)}
        ORDER BY chapter_number, scene_number
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM scene_framework_cards WHERE {' AND '.join(where)}", params[:-2]).fetchone()[0]
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        for k in ("situation", "mind_shift", "desire"):
            d[k] = json_safe(d[k])
        items.append(d)
    return {"total": total, "items": items}


@app.get("/api/nonfiction/arguments")
def api_nonfiction_arguments(book_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    """返回 nonfiction_argument 類型場景（知識論點）"""
    conn = get_db()
    where, params = ["scene_type='nonfiction_argument'"], []
    if book_id:
        where.append("book_id=?"); params.append(book_id)
    sql = f"""
        SELECT chapter_number, scene_number, focal_character, confidence_score,
               match_level, situation, mind_shift, desire, book_id,
               SUBSTR(scene_text,1,200) as scene_text_preview
        FROM scene_framework_cards
        WHERE {' AND '.join(where)}
        ORDER BY chapter_number, scene_number
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM scene_framework_cards WHERE {' AND '.join(where)}", params[:-2]).fetchone()[0]
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        for k in ("situation", "mind_shift", "desire"):
            d[k] = json_safe(d[k])
        items.append(d)
    return {"total": total, "items": items}


@app.get("/api/nonfiction/epistemic")
def api_nonfiction_epistemic(book_id: Optional[str] = None):
    """返回所有 nonfiction 場景，按章節排列，用於概念演化時間軸"""
    conn = get_db()
    where = ["(scene_type='nonfiction_case' OR scene_type='nonfiction_argument')"]
    params = []
    if book_id:
        where.append("book_id=?"); params.append(book_id)
    sql = f"""
        SELECT chapter_number, scene_number, focal_character, scene_type,
               confidence_score, match_level, situation, mind_shift, desire, book_id,
               mind_shift_type, mind_shift_intensity
        FROM scene_framework_cards
        WHERE {' AND '.join(where)}
        ORDER BY chapter_number, scene_number
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        for k in ("situation", "mind_shift", "desire"):
            d[k] = json_safe(d[k])
        items.append(d)
    return items


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """上傳小說 txt / pdf，暫存到 uploads/"""
    filename_lower = (file.filename or "").lower()
    allowed_ext = (".txt", ".pdf")
    if not any(filename_lower.endswith(e) for e in allowed_ext):
        raise HTTPException(400, "只支援 .txt 或 .pdf 格式")

    content = await file.read()

    # ── TXT：自動偵測編碼 ──────────────────────────────────────────────────
    if filename_lower.endswith(".txt"):
        from backend.app.services.scene_splitter import detect_and_decode
        text = detect_and_decode(content)

    # ── PDF：pymupdf 數位提取 / PaddleOCR 掃描件 ──────────────────────────
    elif filename_lower.endswith(".pdf"):
        try:
            from backend.app.services.pdf_ingestor import pdf_to_text
            text = pdf_to_text(content, engine="auto")
        except ImportError as exc:
            raise HTTPException(
                400,
                f"PDF 功能需安裝 pymupdf：pip install pymupdf\n詳情：{exc}",
            ) from exc
        except Exception as exc:
            raise HTTPException(500, f"PDF 解析失敗：{exc}") from exc

        # PDF 轉存為同名 txt 供後續分析流程使用
        txt_filename = Path(file.filename).stem + ".txt"
    else:
        raise HTTPException(400, "不支援的格式")

    if not text or not text.strip():
        raise HTTPException(400, "無法解碼檔案內容，請確認格式與編碼")

    digest = hashlib.sha1(content).hexdigest()[:12]
    book_id = f"book-{digest}"

    # 儲存檔名（pdf → 轉存 txt）
    orig_stem = Path(file.filename or "novel").stem
    save_ext = ".txt"  # 統一儲存為 txt
    save_name = f"{uuid.uuid4().hex[:8]}_{orig_stem}{save_ext}"
    save_path = UPLOAD_DIR / save_name
    save_path.write_text(text, encoding="utf-8")

    # 使用 split_chapters 精確偵測章節數
    from backend.app.services.scene_splitter import split_chapters
    detected_ch = split_chapters(text, book_id=book_id, auto_normalize=False)
    # 過濾掉特殊章節（序章/後記等）讓計數更準確
    real_chapters = [c for c in detected_ch if c.chapter_number < 9000]

    display_name = Path(file.filename or "novel").stem
    registry = load_book_registry()
    registry[book_id] = {
        "book_id": book_id,
        "display_name": display_name,
        "filename": save_name,
        "path": str(save_path),
        "detected_chapters": len(real_chapters),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "source_format": "pdf" if (file.filename or "").lower().endswith(".pdf") else "txt",
    }
    save_book_registry(registry)

    conn = get_db()
    analyzed = conn.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE book_id=?", (book_id,)).fetchone()[0]
    max_ch = conn.execute("SELECT MAX(chapter_number) FROM scene_framework_cards WHERE book_id=?", (book_id,)).fetchone()[0] or 0
    conn.close()

    return {
        "book_id": book_id,
        "display_name": display_name,
        "filename": save_name,
        "path": str(save_path),
        "size_chars": len(text),
        "detected_chapters": len(real_chapters),
        "analyzed_scenes": analyzed,
        "max_analyzed_chapter": max_ch,
        "preview": text[:200],
    }


@app.post("/api/analyze")
async def api_analyze(
    filepath: str = Form(...),
    book_id: str = Form(...),
    chapters_start: int = Form(1),
    chapters_end: int = Form(5),
    mode: str = Form("haiku"),
):
    """觸發批次分析，返回 job_id，前端用 /api/job/{id} 輪詢進度"""
    if not os.path.exists(filepath):
        raise HTTPException(404, "檔案不存在")
    job_id = create_analysis_job(
        filepath=filepath,
        chapters_start=chapters_start,
        chapters_end=chapters_end,
        mode=mode,
        book_id=book_id,
    )
    return {"job_id": job_id}


@app.post("/api/analyze/continue")
async def api_analyze_continue(
    book_id: str = Form(...),
    chapters_end: Optional[int] = Form(None),
    mode: str = Form("haiku"),
):
    registry = load_book_registry()
    book = registry.get(book_id)
    if not book:
        raise HTTPException(404, "找不到書籍資料，請先上傳此書")

    filepath = book.get("path")
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(404, "書籍檔案不存在，請重新上傳")

    conn = get_db()
    max_ch = conn.execute(
        "SELECT MAX(chapter_number) FROM scene_framework_cards WHERE book_id=?",
        (book_id,),
    ).fetchone()[0] or 0
    conn.close()

    next_start = int(max_ch) + 1
    detected_chapters = int(book.get("detected_chapters") or 0)

    if detected_chapters and next_start > detected_chapters:
        return {
            "done": True,
            "message": "本書已分析到最後一章",
            "next_chapter": next_start,
            "detected_chapters": detected_chapters,
        }

    if chapters_end is None:
        if detected_chapters:
            target_end = min(next_start + 9, detected_chapters)
        else:
            target_end = next_start + 9
    else:
        target_end = max(next_start, int(chapters_end))
        if detected_chapters:
            target_end = min(target_end, detected_chapters)

    job_id = create_analysis_job(
        filepath=filepath,
        chapters_start=next_start,
        chapters_end=target_end,
        mode=mode,
        book_id=book_id,
    )
    return {
        "done": False,
        "job_id": job_id,
        "chapters_start": next_start,
        "chapters_end": target_end,
        "detected_chapters": detected_chapters,
    }


@app.get("/api/job/{job_id}")
def api_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "job 不存在")
    j = _jobs[job_id]
    return {
        "status": j["status"],
        "progress": j["progress"],
        "total": j["total"],
        "book_id": j.get("book_id"),
        "chapters_start": j.get("chapters_start"),
        "chapters_end": j.get("chapters_end"),
        "last_lines": j["log"][-10:],
    }


@app.patch("/api/scene/{chapter}/{scene}/negotiation")
def api_update_negotiation(chapter: int, scene: int, body: dict):
    """手動修正談判標籤"""
    is_nego = bool(body.get("is_negotiation_scene", False))
    tags = body.get("negotiation_pattern_tags", [])
    book_id = body.get("book_id")
    conn = get_db()
    if book_id:
        conn.execute("""
            UPDATE scene_framework_cards
            SET is_negotiation_scene=?, negotiation_pattern_tags=?
            WHERE chapter_number=? AND scene_number=? AND book_id=?
        """, (1 if is_nego else 0, json.dumps(tags, ensure_ascii=False), chapter, scene, book_id))
    else:
        conn.execute("""
            UPDATE scene_framework_cards
            SET is_negotiation_scene=?, negotiation_pattern_tags=?
            WHERE chapter_number=? AND scene_number=?
        """, (1 if is_nego else 0, json.dumps(tags, ensure_ascii=False), chapter, scene))
    conn.commit()
    conn.close()
    return {"ok": True}


# ─────────────────────────────────────────────
# Book meta（備注 / 標籤 / book_type）
# ─────────────────────────────────────────────

@app.patch("/api/book/{book_id}/meta")
def api_update_book_meta(book_id: str, body: dict):
    """更新書籍的備注、標籤、book_type（存 book_registry.json）"""
    registry = load_book_registry()
    if book_id not in registry:
        raise HTTPException(status_code=404, detail="book_id 不存在")
    entry = registry[book_id]
    if "notes" in body:
        entry["notes"] = str(body["notes"])
    if "tags" in body:
        raw = body["tags"]
        entry["tags"] = raw if isinstance(raw, list) else []
    if "book_type" in body:
        if body["book_type"] in ("novel", "non_fiction"):
            entry["book_type"] = body["book_type"]
    if "display_name" in body and body["display_name"].strip():
        entry["display_name"] = body["display_name"].strip()
    save_book_registry(registry)
    return {"ok": True, "book_id": book_id, "entry": entry}


# ─────────────────────────────────────────────
# Frontend
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def frontend():
    html_path = ROOT / "frontend" / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>frontend/index.html 不存在</h1>")


if __name__ == "__main__":
    import threading
    import uvicorn
    import webbrowser

    if os.environ.get("NOVEL_NO_BROWSER", "0") != "1":
        # Delay opening slightly so the server is ready when browser connects.
        threading.Timer(0.8, lambda: webbrowser.open("http://localhost:8765/#upload")).start()

    print("🚀 啟動中：http://localhost:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=False)

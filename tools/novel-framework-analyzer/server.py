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
    sql = "SELECT chapter_number, scene_number, focal_character, secondary_characters, match_level, confidence_score, mind_shift_type, mind_shift_intensity, is_negotiation_scene, negotiation_pattern_tags, created_at, book_id FROM scene_framework_cards"
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
        for k in ("scene_labels", "situation", "desire", "mind_shift"):
            d[k] = json_safe(d[k])
        d["scene_text_preview"] = (d.get("scene_text") or "")[:300]
        d.pop("scene_text", None)
        result.append(d)
    return result


@app.get("/api/negotiation")
def api_negotiation(book_id: Optional[str] = None):
    conn = get_db()
    if book_id:
        rows = conn.execute("""
            SELECT chapter_number, scene_number, focal_character,
                   confidence_score, mind_shift_type, negotiation_pattern_tags,
                   situation, desire, mind_shift, scene_text, book_id
            FROM scene_framework_cards
            WHERE is_negotiation_scene=1 AND book_id=?
            ORDER BY chapter_number, scene_number
        """, (book_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT chapter_number, scene_number, focal_character,
                   confidence_score, mind_shift_type, negotiation_pattern_tags,
                   situation, desire, mind_shift, scene_text, book_id
            FROM scene_framework_cards
            WHERE is_negotiation_scene=1
            ORDER BY chapter_number, scene_number
        """).fetchall()
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


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """上傳小說 txt，暫存到 uploads/"""
    if not file.filename.endswith(".txt"):
        raise HTTPException(400, "只支援 .txt 格式")
    content = await file.read()
    # 嘗試 UTF-8，再試 GBK
    for enc in ("utf-8", "gbk", "big5"):
        try:
            text = content.decode(enc)
            break
        except Exception:
            text = None
    if not text:
        raise HTTPException(400, "無法解碼檔案，請確認編碼（UTF-8 / GBK）")

    digest = hashlib.sha1(content).hexdigest()[:12]
    book_id = f"book-{digest}"

    save_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = UPLOAD_DIR / save_name
    save_path.write_text(text, encoding="utf-8")

    # 偵測章節數
    import re
    chapters = re.findall(r"第[零一二三四五六七八九十百千\d]+章", text)

    registry = load_book_registry()
    registry[book_id] = {
        "book_id": book_id,
        "display_name": Path(file.filename).stem,
        "filename": save_name,
        "path": str(save_path),
        "detected_chapters": len(chapters),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_book_registry(registry)

    conn = get_db()
    analyzed = conn.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE book_id=?", (book_id,)).fetchone()[0]
    max_ch = conn.execute("SELECT MAX(chapter_number) FROM scene_framework_cards WHERE book_id=?", (book_id,)).fetchone()[0] or 0
    conn.close()

    return {
        "book_id": book_id,
        "display_name": Path(file.filename).stem,
        "filename": save_name,
        "path": str(save_path),
        "size_chars": len(text),
        "detected_chapters": len(chapters),
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

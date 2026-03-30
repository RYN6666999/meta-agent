"""
server.py — 局心欲變分析系統 Web 介面
執行：python3 server.py
開啟：http://localhost:8765
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import uuid
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


# ─────────────────────────────────────────────
# API routes
# ─────────────────────────────────────────────

@app.get("/api/summary")
def api_summary():
    conn = get_db()
    cur = conn.cursor()
    total    = cur.execute("SELECT COUNT(*) FROM scene_framework_cards").fetchone()[0]
    nego     = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE is_negotiation_scene=1").fetchone()[0]
    decisions = cur.execute("SELECT COUNT(*) FROM scene_framework_cards WHERE scene_labels LIKE '%decision%'").fetchone()[0]
    max_ch   = cur.execute("SELECT MAX(chapter_number) FROM scene_framework_cards").fetchone()[0] or 0
    avg_conf = cur.execute("SELECT AVG(confidence_score) FROM scene_framework_cards").fetchone()[0] or 0
    chars    = cur.execute("""
        SELECT focal_character, COUNT(*) n FROM scene_framework_cards
        GROUP BY focal_character ORDER BY n DESC LIMIT 6
    """).fetchall()
    shifts   = cur.execute("""
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


@app.get("/api/scenes")
def api_scenes(
    chapter: Optional[int] = None,
    char: Optional[str] = None,
    match: Optional[str] = None,
    negotiation: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
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
    sql = "SELECT chapter_number, scene_number, focal_character, secondary_characters, match_level, confidence_score, mind_shift_type, mind_shift_intensity, is_negotiation_scene, negotiation_pattern_tags, created_at FROM scene_framework_cards"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY chapter_number, scene_number LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = cur.fetchall() if False else cur.execute(sql, params).fetchall()
    total = cur.execute("SELECT COUNT(*) FROM scene_framework_cards" + (" WHERE " + " AND ".join(where) if where else ""), params[:-2]).fetchone()[0]
    conn.close()
    return {
        "total": total,
        "items": [dict(r) for r in rows],
    }


@app.get("/api/scene/{chapter}/{scene}")
def api_scene_detail(chapter: int, scene: int):
    conn = get_db()
    cur = conn.cursor()
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
def api_decisions():
    """行動決策場景：scene_labels 含 'decision'"""
    conn = get_db()
    rows = conn.execute("""
        SELECT chapter_number, scene_number, focal_character,
               confidence_score, match_level, mind_shift_type, mind_shift_intensity,
               scene_labels, situation, desire, mind_shift, scene_text
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
def api_negotiation():
    conn = get_db()
    rows = conn.execute("""
        SELECT chapter_number, scene_number, focal_character,
               confidence_score, mind_shift_type, negotiation_pattern_tags,
               situation, desire, mind_shift, scene_text
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
def api_arc(character: str):
    conn = get_db()
    rows = conn.execute("""
        SELECT chapter_number, scene_number, mind_shift_type, mind_shift_intensity,
               match_level, confidence_score, mind_shift, is_negotiation_scene
        FROM scene_framework_cards
        WHERE focal_character=?
        ORDER BY chapter_number, scene_number
    """, (character,)).fetchall()
    conn.close()
    type_score = {"none":0,"emotion":1,"stance":2,"strategy":3,"values":4,"identity":5}
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

    save_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = UPLOAD_DIR / save_name
    save_path.write_text(text, encoding="utf-8")

    # 偵測章節數
    import re
    chapters = re.findall(r"第[零一二三四五六七八九十百千\d]+章", text)
    return {
        "filename": save_name,
        "path": str(save_path),
        "size_chars": len(text),
        "detected_chapters": len(chapters),
        "preview": text[:200],
    }


@app.post("/api/analyze")
async def api_analyze(
    filepath: str = Form(...),
    chapters_start: int = Form(1),
    chapters_end: int = Form(5),
    mode: str = Form("haiku"),
):
    """觸發批次分析，返回 job_id，前端用 /api/job/{id} 輪詢進度"""
    if not os.path.exists(filepath):
        raise HTTPException(404, "檔案不存在")
    job_id = uuid.uuid4().hex[:10]
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 0, "log": []}

    async def run_job():
        import subprocess
        cmd = [
            sys.executable, str(ROOT / "scripts" / "batch_analyze.py"),
            "--chapters", f"{chapters_start}-{chapters_end}",
            "--mode", mode,
            "--skip-existing",
        ]
        env = os.environ.copy()
        env["NOVEL_PATH_OVERRIDE"] = filepath

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
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def api_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "job 不存在")
    j = _jobs[job_id]
    return {
        "status": j["status"],
        "progress": j["progress"],
        "total": j["total"],
        "last_lines": j["log"][-10:],
    }


@app.patch("/api/scene/{chapter}/{scene}/negotiation")
def api_update_negotiation(chapter: int, scene: int, body: dict):
    """手動修正談判標籤"""
    is_nego = bool(body.get("is_negotiation_scene", False))
    tags = body.get("negotiation_pattern_tags", [])
    conn = get_db()
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
    import uvicorn
    print("🚀 啟動中：http://localhost:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=False)

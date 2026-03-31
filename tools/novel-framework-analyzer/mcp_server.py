#!/usr/bin/env python3
"""
mcp_server.py  ─  Novel Framework Analyzer MCP Server
======================================================
讓任何支援 MCP 的 AI（Claude Desktop / Cursor / Windsurf / claude.ai 等）
直接查詢小說場景分析資料。

傳輸模式：
  stdio  ← 本機 Claude Desktop / Cursor（預設）
  sse    ← 遠端 HTTP 連線（部署到伺服器後使用）

啟動方式：
  # 本機 stdio 模式
  python3 mcp_server.py

  # 遠端 SSE 模式（部署後）
  python3 mcp_server.py --transport sse --host 0.0.0.0 --port 9400

環境變數：
  NOVEL_DB_PATH      SQLite 路徑（預設：同目錄下 novel_analyzer.db）
  NOVEL_VECTOR_PATH  ChromaDB 路徑（預設：vector_store/chroma）
  NOVEL_EMBED_MODEL  embedding 模型（預設：paraphrase-multilingual-MiniLM-L12-v2）
  LIGHTRAG_API       memory-mcp LightRAG 端點（預設：http://127.0.0.1:9631）
  MCP_API_KEY        SSE 模式的 Bearer token（留空 = 不驗證，僅本機用）
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# ── 路徑設定 ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("NOVEL_DB_PATH", str(BASE_DIR / "novel_analyzer.db"))
VECTOR_PATH = os.environ.get("NOVEL_VECTOR_PATH", str(BASE_DIR / "vector_store" / "chroma"))
EMBED_MODEL = os.environ.get("NOVEL_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
LIGHTRAG_API = os.environ.get("LIGHTRAG_API", "http://127.0.0.1:9631")

import sys
sys.path.insert(0, str(BASE_DIR))

# ── MCP Server 初始化 ─────────────────────────────────────────────────────────
mcp = FastMCP(
    "novel-analyzer",
    instructions=(
        "小說框架分析知識庫。包含場景欲望/情境/心理轉變/判斷四維分析卡。"
        "可查詢特定章節場景、語義搜尋、角色弧線、決策場景等。"
    ),
)

# ── 資料庫連線（每次查詢新建，避免多 thread 衝突）────────────────────────────
def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for key in ("situation", "desire", "mind_shift", "judgment",
                "secondary_characters", "negotiation_pattern_tags", "scene_labels"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d

# ── ChromaDB（延遲載入，未建索引時跳過）──────────────────────────────────────
_chroma: Any = None

def _get_chroma():
    global _chroma
    if _chroma is None:
        vector_dir = Path(VECTOR_PATH)
        if not vector_dir.exists():
            return None
        try:
            from services.vector_store.chroma_adapter import ChromaAdapter
            _chroma = ChromaAdapter(persist_path=VECTOR_PATH, model_name=EMBED_MODEL)
        except Exception:
            return None
    return _chroma


# ════════════════════════════════════════════════════════════════════════════
#  MCP 工具定義
# ════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_books() -> str:
    """列出所有已分析的書籍，包含章數、場景數、分析卡數統計。"""
    with _db() as conn:
        rows = conn.execute("""
            SELECT book_id,
                   COUNT(*)                       AS total_cards,
                   COUNT(DISTINCT chapter_number) AS chapters,
                   COUNT(DISTINCT scene_id)       AS scenes,
                   MIN(created_at)                AS first_analyzed,
                   MAX(created_at)                AS last_analyzed
            FROM scene_framework_cards
            GROUP BY book_id
        """).fetchall()
    if not rows:
        return "資料庫中尚無書籍資料，請先執行批次分析。"
    result = []
    for r in rows:
        result.append(
            f"書籍 ID: {r['book_id']}\n"
            f"  分析卡: {r['total_cards']} 筆｜章節: {r['chapters']} 章｜場景: {r['scenes']} 個\n"
            f"  首次分析: {r['first_analyzed'][:10]}  最後更新: {r['last_analyzed'][:10]}"
        )
    return "\n\n".join(result)


@mcp.tool()
def get_scene(chapter: int, scene: int, book_id: Optional[str] = None) -> str:
    """
    取得特定章節場景的完整框架分析卡。

    Args:
        chapter: 章節編號（整數）
        scene:   場景編號（整數，從 1 開始）
        book_id: 書籍 ID（可省略，有多本書時必填）

    Returns:
        該場景的欲望、情境、心理轉變、判斷四維分析，以及原文片段。
    """
    query = "SELECT * FROM scene_framework_cards WHERE chapter_number=? AND scene_number=?"
    params: list = [chapter, scene]
    if book_id:
        query += " AND book_id=?"
        params.append(book_id)
    query += " LIMIT 1"

    with _db() as conn:
        row = conn.execute(query, params).fetchone()

    if not row:
        return f"找不到第 {chapter} 章場景 {scene} 的分析卡。"

    d = _row_to_dict(row)
    situation = d.get("situation", {})
    desire = d.get("desire", {})
    mind_shift = d.get("mind_shift", {})
    judgment = d.get("judgment", {})

    return (
        f"## 第{chapter}章 場景{scene}｜{d.get('focal_character', '未知')}視角\n\n"
        f"**場景原文（前300字）**\n{d.get('scene_text', '')[:300]}...\n\n"
        f"**局 Situation**\n"
        f"  外部局勢：{situation.get('external_situation', '—')}\n"
        f"  權力動態：{situation.get('power_dynamics', '—')}\n"
        f"  主動方：{situation.get('active_party', '—')} ｜ 被動方：{situation.get('passive_party', '—')}\n\n"
        f"**欲 Desire**\n"
        f"  顯性欲望：{desire.get('explicit_desire', '—')}\n"
        f"  隱性欲望：{desire.get('implicit_desire', '—')}\n"
        f"  真正目標：{desire.get('true_objective', '—')}\n\n"
        f"**心 Mind → 變 Shift**\n"
        f"  類型：{d.get('mind_shift_type', '—')}（強度 {d.get('mind_shift_intensity', 0)}/5）\n"
        f"  進入場景：{mind_shift.get('before_mindset', '—')}\n"
        f"  觸發事件：{mind_shift.get('trigger_event', '—')}\n"
        f"  離開場景：{mind_shift.get('after_mindset', '—')}\n\n"
        f"**框架判定**\n{judgment.get('reasoning', '—')}\n\n"
        f"**配對等級**：{d.get('match_level', '—')}｜信心分數：{d.get('confidence_score', 0):.2f}\n"
        f"**談判場景**：{'是' if d.get('is_negotiation_scene') else '否'}\n"
        f"**場景標籤**：{', '.join(d.get('scene_labels') or []) or '無'}"
    )


@mcp.tool()
async def search_scenes(
    query: str,
    top_k: int = 5,
    book_id: Optional[str] = None,
    min_score: float = 0.5,
) -> str:
    """
    用自然語言語義搜尋場景分析卡（需先執行 python scripts/index_vectors.py 建立向量索引）。

    Args:
        query:     自然語言查詢，例如「謝雲初為何改變立場」「談判失敗的場景」
        top_k:     返回結果數量（預設 5，最多 20）
        book_id:   限定書籍（可省略）
        min_score: 最低相似度門檻（0~1，預設 0.5）

    Returns:
        最相關場景列表，含章節位置、主角、相似度評分與摘要。
    """
    chroma = _get_chroma()
    if chroma is None:
        return (
            "⚠️ 向量索引尚未建立或 ChromaDB 未安裝。\n"
            "請先執行：python scripts/index_vectors.py\n"
            "並安裝：pip install chromadb sentence-transformers"
        )

    from services.vector_store.base import RetrievalRequest

    req = RetrievalRequest(
        query=query,
        top_k=min(top_k, 20),
        score_threshold=min_score,
        filters={"book_id": book_id} if book_id else {},
    )

    results = await chroma.retrieve(req)

    if not results:
        return f"未找到與「{query}」相關的場景（相似度 < {min_score}）。"

    lines = [f"語義搜尋：「{query}」— 找到 {len(results)} 筆\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. **{r.source_reference}** ｜相似度 {r.score:.2f}\n"
            f"   主角：{', '.join(r.metadata.focal_characters)}\n"
            f"   {r.text[:120]}..."
        )
    return "\n".join(lines)


@mcp.tool()
def get_character_arc(character: str, book_id: Optional[str] = None) -> str:
    """
    取得角色的心理轉變弧線（按章節順序列出所有心理轉變場景）。

    Args:
        character: 角色名稱，例如「謝雲初」「寧凡」
        book_id:   書籍 ID（可省略）

    Returns:
        按章節順序排列的心理轉變記錄，顯示轉變類型、強度與描述。
    """
    query = """
        SELECT chapter_number, scene_number, mind_shift_type, mind_shift_intensity,
               mind_shift, judgment, match_level, confidence_score
        FROM scene_framework_cards
        WHERE focal_character = ?
    """
    params: list = [character]
    if book_id:
        query += " AND book_id = ?"
        params.append(book_id)
    query += " AND mind_shift_type != 'none' ORDER BY chapter_number, scene_number"

    with _db() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        # 嘗試模糊搜尋
        with _db() as conn:
            like_rows = conn.execute(
                "SELECT DISTINCT focal_character FROM scene_framework_cards WHERE focal_character LIKE ?",
                [f"%{character}%"],
            ).fetchall()
        if like_rows:
            names = [r["focal_character"] for r in like_rows]
            return f"找不到角色「{character}」。您是否要找：{', '.join(names)}？"
        return f"找不到角色「{character}」的任何場景。"

    lines = [f"## {character} 心理轉變弧線（{len(rows)} 個轉折點）\n"]
    for r in rows:
        ms = r["mind_shift"]
        if isinstance(ms, str):
            try:
                ms = json.loads(ms)
            except Exception:
                ms = {}
        desc = ms.get("description", "—") if isinstance(ms, dict) else "—"
        intensity_bar = "█" * int(r["mind_shift_intensity"] or 0) + "░" * (5 - int(r["mind_shift_intensity"] or 0))
        lines.append(
            f"**第{r['chapter_number']}章 場景{r['scene_number']}**\n"
            f"  轉變類型：{r['mind_shift_type']}｜強度 [{intensity_bar}]\n"
            f"  {desc}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def list_characters(book_id: Optional[str] = None) -> str:
    """
    列出所有出現的主角角色及其場景數量統計。

    Args:
        book_id: 書籍 ID（可省略，有多本書時建議填寫）
    """
    query = """
        SELECT focal_character,
               COUNT(*) AS scene_count,
               COUNT(CASE WHEN mind_shift_type != 'none' THEN 1 END) AS shift_scenes,
               AVG(confidence_score) AS avg_confidence
        FROM scene_framework_cards
    """
    params: list = []
    if book_id:
        query += " WHERE book_id = ?"
        params.append(book_id)
    query += " GROUP BY focal_character ORDER BY scene_count DESC"

    with _db() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return "無角色資料。"

    lines = ["角色列表（按場景數排序）：\n"]
    for r in rows:
        lines.append(
            f"• **{r['focal_character']}** — "
            f"{r['scene_count']} 場景，{r['shift_scenes']} 個心理轉折，"
            f"平均信心 {r['avg_confidence']:.2f}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_negotiation_scenes(
    book_id: Optional[str] = None,
    character: Optional[str] = None,
    limit: int = 10,
) -> str:
    """
    取得談判/決策場景列表（is_negotiation_scene = true 的場景）。

    Args:
        book_id:   書籍 ID（可省略）
        character: 篩選特定主角（可省略）
        limit:     返回筆數（預設 10，最多 50）

    Returns:
        談判場景列表，含談判模式標籤和判斷結果。
    """
    conditions = ["is_negotiation_scene = 1"]
    params: list = []
    if book_id:
        conditions.append("book_id = ?")
        params.append(book_id)
    if character:
        conditions.append("focal_character = ?")
        params.append(character)

    query = (
        "SELECT chapter_number, scene_number, focal_character, "
        "negotiation_pattern_tags, judgment, confidence_score "
        f"FROM scene_framework_cards WHERE {' AND '.join(conditions)} "
        f"ORDER BY chapter_number, scene_number LIMIT {min(limit, 50)}"
    )

    with _db() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return "沒有符合條件的談判場景。"

    lines = [f"談判場景（共 {len(rows)} 筆）：\n"]
    for r in rows:
        tags = r["negotiation_pattern_tags"]
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        tags_str = ", ".join(tags) if tags else "無標籤"

        judgment = r["judgment"]
        if isinstance(judgment, str):
            try:
                judgment = json.loads(judgment)
            except Exception:
                judgment = {}
        j_desc = (judgment.get("description", "—") if isinstance(judgment, dict) else "—")[:80]

        lines.append(
            f"**第{r['chapter_number']}章 場景{r['scene_number']}** ｜{r['focal_character']}\n"
            f"  模式：{tags_str}\n"
            f"  判斷：{j_desc}...\n"
        )
    return "\n".join(lines)


@mcp.tool()
def filter_scenes(
    match_level: Optional[str] = None,
    mind_shift_type: Optional[str] = None,
    book_id: Optional[str] = None,
    chapter_from: Optional[int] = None,
    chapter_to: Optional[int] = None,
    limit: int = 15,
) -> str:
    """
    依條件篩選場景卡（結構化過濾，與 search_scenes 語義搜尋互補）。

    Args:
        match_level:     配對等級篩選（full / partial / weak / none）
        mind_shift_type: 心理轉變類型（emotion / values / strategy / identity / stance / none）
        book_id:         書籍 ID
        chapter_from:    起始章節（包含）
        chapter_to:      結束章節（包含）
        limit:           返回筆數（預設 15，最多 50）

    Returns:
        符合條件的場景卡摘要列表。
    """
    conditions: list = []
    params: list = []

    if match_level:
        conditions.append("match_level = ?")
        params.append(match_level)
    if mind_shift_type:
        conditions.append("mind_shift_type = ?")
        params.append(mind_shift_type)
    if book_id:
        conditions.append("book_id = ?")
        params.append(book_id)
    if chapter_from:
        conditions.append("chapter_number >= ?")
        params.append(chapter_from)
    if chapter_to:
        conditions.append("chapter_number <= ?")
        params.append(chapter_to)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = (
        f"SELECT chapter_number, scene_number, focal_character, "
        f"match_level, mind_shift_type, mind_shift_intensity, confidence_score "
        f"FROM scene_framework_cards {where} "
        f"ORDER BY chapter_number, scene_number LIMIT {min(limit, 50)}"
    )

    with _db() as conn:
        rows = conn.execute(query, params).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM scene_framework_cards {where}", params
        ).fetchone()[0]

    if not rows:
        return "沒有符合條件的場景。"

    lines = [f"篩選結果（符合 {total} 筆，顯示前 {len(rows)} 筆）：\n"]
    for r in rows:
        lines.append(
            f"第{r['chapter_number']}章 場景{r['scene_number']} ｜{r['focal_character']}"
            f"｜{r['match_level']}｜{r['mind_shift_type']}(強度{r['mind_shift_intensity']})"
            f"｜信心{r['confidence_score']:.2f}"
        )
    return "\n".join(lines)


@mcp.tool()
async def ingest_to_memory(
    chapter: int,
    scene: int,
    book_id: Optional[str] = None,
    memo: Optional[str] = None,
) -> str:
    """
    將指定場景的分析卡匯入到 memory-mcp（LightRAG 知識圖譜），
    讓其他 AI Agent 也能透過 memory-mcp 查到這筆分析。

    Args:
        chapter: 章節編號
        scene:   場景編號
        book_id: 書籍 ID（可省略）
        memo:    附加備注（例如「這是關鍵轉折點」）

    Returns:
        匯入結果。
    """
    import httpx

    # 先拿場景資料
    query_sql = "SELECT * FROM scene_framework_cards WHERE chapter_number=? AND scene_number=?"
    p: list = [chapter, scene]
    if book_id:
        query_sql += " AND book_id=?"
        p.append(book_id)
    query_sql += " LIMIT 1"

    with _db() as conn:
        row = conn.execute(query_sql, p).fetchone()

    if not row:
        return f"找不到第{chapter}章場景{scene}的分析卡，無法匯入。"

    d = _row_to_dict(row)
    focal = d.get("focal_character", "未知")
    situation = d.get("situation", {})
    desire = d.get("desire", {})
    mind_shift = d.get("mind_shift", {})
    judgment = d.get("judgment", {})

    content = (
        f"[小說場景分析] 第{chapter}章 場景{scene}｜{focal}視角\n"
        f"書籍ID：{d.get('book_id')}\n"
        f"外部局勢：{situation.get('external_situation', '—')}\n"
        f"顯性欲望：{desire.get('explicit_desire', '—')}\n"
        f"隱性欲望：{desire.get('implicit_desire', '—')}\n"
        f"心理轉變({d.get('mind_shift_type', '—')},強度{d.get('mind_shift_intensity')}): "
        f"{mind_shift.get('before_mindset', '—')} → {mind_shift.get('after_mindset', '—')}\n"
        f"觸發事件：{mind_shift.get('trigger_event', '—')}\n"
        f"判斷理由：{judgment.get('reasoning', '—')}\n"
        f"配對等級：{d.get('match_level')}｜信心：{d.get('confidence_score', 0):.2f}\n"
    )
    if memo:
        content += f"\n備注：{memo}"

    # 呼叫 LightRAG ingest API
    async def _ingest() -> str:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{LIGHTRAG_API}/documents/text",
                    json={"text": content, "description": f"小說場景 第{chapter}章場景{scene}"},
                )
                if resp.status_code in (200, 201):
                    return f"✅ 已匯入 LightRAG（第{chapter}章場景{scene}，主角：{focal}）"
                return f"❌ LightRAG 回應 {resp.status_code}：{resp.text[:200]}"
        except httpx.ConnectError:
            return (
                f"❌ 無法連線 LightRAG（{LIGHTRAG_API}）。\n"
                "請確認 memory-mcp 的 LightRAG 服務是否正在執行。"
            )

    return await _ingest()


# ════════════════════════════════════════════════════════════════════════════
#  啟動
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Novel Analyzer MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="傳輸模式：stdio（本機）或 sse（遠端 HTTP）",
    )
    parser.add_argument("--host", default="0.0.0.0", help="SSE 模式綁定位址")
    parser.add_argument("--port", type=int, default=9400, help="SSE 模式端口（預設 9400）")
    args = parser.parse_args()

    if not Path(DB_PATH).exists():
        print(f"[警告] 找不到資料庫：{DB_PATH}", flush=True)
        print("請先執行：python scripts/batch_analyze.py", flush=True)

    if args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # 在 Cloudflare Tunnel 後方，DNS rebinding 保護由 CF 處理，本地關閉即可
        if mcp.settings.transport_security is not None:
            mcp.settings.transport_security.enable_dns_rebinding_protection = False
        print(f"[Novel MCP] SSE 模式啟動 → http://{args.host}:{args.port}/sse", flush=True)
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
memory-mcp/server.py — 記憶黑盒 MCP 伺服器
共用大腦：Claude / Golem / Nanoclaw 共用同一個記憶後端

4 個工具：
  query_memory(q)                  → LightRAG 語意搜尋
  ingest_memory(content, type)     → 存入圖譜
  get_rules()                      → 讀 law.json
  log_error(root_cause, solution)  → 寫 error-log + ingest
"""

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ── 常數 ─────────────────────────────────────────────────────────────
LIGHTRAG_API = "http://localhost:9621"
LAW_JSON = Path("/Users/ryan/meta-agent/law.json")
ERROR_LOG_DIR = Path("/Users/ryan/meta-agent/error-log")
META_AGENT_DIR = Path("/Users/ryan/meta-agent")
TODAY = date.today().isoformat

# P3-B：觸發強化 — 更新 last_triggered + score_boost
MEMORY_SCAN_DIRS = [
    META_AGENT_DIR / "error-log",
    META_AGENT_DIR / "truth-source",
    META_AGENT_DIR / "memory",
]
BOOST_MULTIPLIER = 1.2
MAX_BASE_SCORE = 150.0


def _update_last_triggered(query: str) -> int:
    """
    P3-B：掃描本地記憶檔案，更新與 query 相關的 last_triggered + score_boost。
    回傳更新的檔案數量。
    """
    today = date.today().isoformat()
    # 提取關鍵詞（最多 8 個）
    keywords = [kw.lower() for kw in re.split(r"[\s，。？！、]+", query) if len(kw) >= 2][:8]
    if not keywords:
        return 0

    updated = 0
    for scan_dir in MEMORY_SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                text_lower = text.lower()
                # 至少 2 個關鍵詞匹配才更新
                matches = sum(1 for kw in keywords if kw in text_lower)
                if matches < 2:
                    continue

                # 更新 last_triggered
                if "last_triggered:" in text:
                    text = re.sub(
                        r"last_triggered:\s*\S+",
                        f"last_triggered: {today}",
                        text,
                    )

                # 更新 score_boost（base_score × 1.2，上限 150）
                boost_match = re.search(r"base_score:\s*([\d.]+)", text)
                if boost_match:
                    old_score = float(boost_match.group(1))
                    new_score = min(old_score * BOOST_MULTIPLIER, MAX_BASE_SCORE)
                    text = re.sub(
                        r"base_score:\s*[\d.]+",
                        f"base_score: {new_score:.1f}",
                        text,
                    )
                else:
                    # 沒有 base_score 欄位 → 在 last_triggered 後插入（初始 100 × 1.2 = 120）
                    text = re.sub(
                        r"(last_triggered:\s*\S+)",
                        r"\1\nbase_score: 120.0",
                        text,
                        count=1,
                    )

                md_file.write_text(text, encoding="utf-8")
                updated += 1

            except Exception:
                continue

    return updated


def _check_conflicts(content: str, title: str) -> Optional[str]:
    """
    P4-A：矛盾檢查（同步版本，用於 ingest_memory 呼叫前）。
    掃描本地 error-log/ 和 truth-source/ 找關鍵詞重疊的文件。
    回傳警告字串，若無衝突回傳 None。
    """
    keywords = [kw.lower() for kw in re.split(r"[\s，。？！、]+", title + " " + content[:200])
                if len(kw) >= 3][:10]
    if not keywords:
        return None

    conflicts = []
    check_dirs = [META_AGENT_DIR / "error-log", META_AGENT_DIR / "truth-source"]
    for scan_dir in check_dirs:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            try:
                text_lower = md_file.read_text(encoding="utf-8").lower()
                matches = sum(1 for kw in keywords if kw in text_lower)
                if matches >= 3:
                    conflicts.append(md_file.name)
            except Exception:
                continue

    if conflicts:
        return (
            f"⚠️  矛盾檢查：找到 {len(conflicts)} 個可能衝突的現有文件：\n"
            + "\n".join(f"  - {c}" for c in conflicts[:5])
            + "\n\n請確認新內容不與現有知識矛盾。若確定要 ingest，"
            "請在 content 開頭加入 `[CONFIRMED]` 標記。"
        )
    return None

VALID_TYPES = {"error_fix", "tech_decision", "verified_truth", "rule", "deprecated"}

# ── FastMCP 初始化 ────────────────────────────────────────────────────
mcp = FastMCP(
    name="memory-mcp",
    instructions=(
        "meta-agent 記憶黑盒。提供語意搜尋、知識 ingest、"
        "規則查詢、錯誤記錄四個工具。"
        "所有 AI 工具（Claude/Golem/Nanoclaw）共用此後端。"
    ),
)


# ── 工具 1：query_memory ──────────────────────────────────────────────
@mcp.tool()
async def query_memory(q: str, mode: str = "hybrid") -> str:
    """
    語意搜尋 LightRAG 知識圖譜。

    Args:
        q: 搜尋查詢（中英文均可）
        mode: 搜尋模式 hybrid / local / global / naive（預設 hybrid）

    Returns:
        搜尋結果文字
    """
    if mode not in ("hybrid", "local", "global", "naive"):
        mode = "hybrid"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{LIGHTRAG_API}/query",
            json={"query": q, "mode": mode},
        )
        resp.raise_for_status()
        data = resp.json()

    result = data.get("response") or data.get("result") or str(data)

    # P3-B：觸發強化 — 更新本地相關記憶的 last_triggered + score_boost
    updated = _update_last_triggered(q)
    boost_note = f"\n[記憶強化：{updated} 個相關文件 last_triggered 已更新]" if updated > 0 else ""

    return f"[LightRAG {mode}]\n{result}{boost_note}"


# ── 工具 2：ingest_memory ─────────────────────────────────────────────
@mcp.tool()
async def ingest_memory(content: str, mem_type: str = "verified_truth", title: str = "") -> str:
    """
    將知識存入 LightRAG 圖譜（附 frontmatter）。

    Args:
        content: 知識內容（<3000字，法典禁止超過 4000）
        mem_type: 類型 error_fix / tech_decision / verified_truth / rule
        title: 簡短標題（選填）

    Returns:
        ingest 結果
    """
    # 法典：禁止 ingest 前不加字數驗證
    if len(content) < 50:
        return "❌ 內容太短（<50字），拒絕 ingest（防止髒資料）"

    if len(content) > 4000:
        return "❌ 內容超過 4000 字（法典禁止），請拆分後分批 ingest"

    if mem_type not in VALID_TYPES:
        mem_type = "verified_truth"

    # P4-A：矛盾檢查 — ingest 前先驗證
    # [CONFIRMED] 標記可跳過檢查（使用者已確認）
    if not content.startswith("[CONFIRMED]"):
        conflict_warning = _check_conflicts(content, title or content[:80])
        if conflict_warning:
            return conflict_warning

    today = date.today().isoformat()
    title = title or content[:40].replace("\n", " ")
    expires = {"error_fix": 365, "tech_decision": 730, "rule": 180}.get(mem_type, 365)

    doc = (
        f"---\n"
        f"date: {today}\n"
        f"type: {mem_type}\n"
        f"status: active\n"
        f"last_triggered: {today}\n"
        f"expires_after_days: {expires}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content}\n"
    )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{LIGHTRAG_API}/documents/text",
            json={"text": doc, "description": title},
        )
        resp.raise_for_status()
        data = resp.json()

    return f"✅ Ingest 成功：{title}\n狀態：{data}"


# ── 工具 3：get_rules ─────────────────────────────────────────────────
@mcp.tool()
def get_rules(category: str = "all") -> str:
    """
    讀取 law.json 硬規則法典。

    Args:
        category: all / forbidden / n8n_rules / memory_rules / tech_stack / git_score

    Returns:
        JSON 格式的規則
    """
    if not LAW_JSON.exists():
        return "❌ 找不到 law.json"

    data = json.loads(LAW_JSON.read_text(encoding="utf-8"))

    if category == "all":
        return json.dumps(data, ensure_ascii=False, indent=2)

    section = data.get(category)
    if section is None:
        available = list(data.keys())
        return f"❌ 找不到分類 '{category}'。可用：{available}"

    return json.dumps({category: section}, ensure_ascii=False, indent=2)


# ── 工具 4：log_error ─────────────────────────────────────────────────
@mcp.tool()
async def log_error(root_cause: str, solution: str, topic: str = "", context: str = "") -> str:
    """
    記錄錯誤到 error-log/ + ingest 到 LightRAG。

    Args:
        root_cause: 根本原因（必填）
        solution: 解決方案（必填）
        topic: 錯誤主題（用於檔名，英文，例如 n8n-webhook）
        context: 額外背景資訊（選填）

    Returns:
        寫入結果
    """
    if not root_cause or not solution:
        return "❌ root_cause 和 solution 均為必填"

    today = date.today().isoformat()
    safe_topic = re.sub(r"[^\w-]", "-", topic.lower()) if topic else "general"
    filename = f"{today}-{safe_topic}.md"
    filepath = ERROR_LOG_DIR / filename

    content = (
        f"---\n"
        f"date: {today}\n"
        f"type: error_fix\n"
        f"status: active\n"
        f"last_triggered: {today}\n"
        f"expires_after_days: 365\n"
        f"topic: {safe_topic}\n"
        f"---\n\n"
        f"# Error: {root_cause[:60]}\n\n"
        f"## 根本原因\n{root_cause}\n\n"
        f"## 解決方案\n{solution}\n"
    )

    if context:
        content += f"\n## 背景\n{context}\n"

    # 寫入 error-log/
    ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")

    # ingest 到 LightRAG
    ingest_result = await ingest_memory(
        content=f"根因：{root_cause}\n解法：{solution}\n{context}",
        mem_type="error_fix",
        title=f"Error Fix: {root_cause[:50]}",
    )

    return f"✅ 已寫入 {filepath}\n{ingest_result}"


# ── 入口 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()

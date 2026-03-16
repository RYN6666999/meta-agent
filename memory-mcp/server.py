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
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ── 常數 ─────────────────────────────────────────────────────────────
LIGHTRAG_API = "http://localhost:9621"
LAW_JSON = Path("/Users/ryan/meta-agent/law.json")
ERROR_LOG_DIR = Path("/Users/ryan/meta-agent/error-log")
META_AGENT_DIR = Path("/Users/ryan/meta-agent")
USERS_DIR = META_AGENT_DIR / "memory" / "users"
TODAY = date.today().isoformat()
# Workflow C：錯誤歸檔 webhook（fire-and-forget，不阻塞主流程）
ERROR_ARCHIVE_WEBHOOK = "http://localhost:5678/webhook/3E3yP5pGX1GepMuu/webhook/error-archive"

# P3-B：觸發強化 — 更新 last_triggered + score_boost
MEMORY_SCAN_DIRS = [
    META_AGENT_DIR / "error-log",
    META_AGENT_DIR / "truth-source",
    META_AGENT_DIR / "memory",
]
BOOST_MULTIPLIER = 1.2
MAX_BASE_SCORE = 150.0

RISKY_TYPES = {"rule", "tech_decision"}
RISKY_KEYWORDS = {
    "delete",
    "drop",
    "truncate",
    "override",
    "forbidden",
    "law",
    "policy",
    "api_key",
    "token",
    "secret",
}


def _parse_frontmatter_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_title(text: str) -> str:
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return title_match.group(1).strip() if title_match else "(untitled)"


def _compute_rerank_score(text: str, keywords: list[str]) -> tuple[float, dict]:
    lowered = text.lower()
    hit_count = sum(1 for kw in keywords if kw in lowered)
    keyword_score = (hit_count / max(len(keywords), 1)) * 5.0

    confidence_raw = _parse_frontmatter_value(text, "confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw else 0.7
    except ValueError:
        confidence = 0.7

    usage_raw = _parse_frontmatter_value(text, "usage_count")
    try:
        usage_count = max(int(float(usage_raw)), 0) if usage_raw else 0
    except ValueError:
        usage_count = 0

    last_triggered = _parse_frontmatter_value(text, "last_triggered")
    freshness_score = 0.0
    if last_triggered:
        try:
            delta_days = (date.today() - datetime.strptime(last_triggered, "%Y-%m-%d").date()).days
            freshness_score = max(0.0, 2.0 - (delta_days * 0.05))
        except ValueError:
            freshness_score = 0.0

    usage_score = min(2.0, usage_count * 0.1)
    confidence_score = max(0.0, min(confidence, 1.0)) * 3.0
    total = keyword_score + confidence_score + freshness_score + usage_score

    return total, {
        "keyword_score": round(keyword_score, 2),
        "confidence": round(confidence, 2),
        "freshness_score": round(freshness_score, 2),
        "usage_count": usage_count,
        "usage_score": round(usage_score, 2),
    }


def _local_rerank_candidates(query: str, limit: int = 3, max_scan_files: int = 220, user_id: str = "default") -> list[dict]:
    keywords = [kw.lower() for kw in re.split(r"[\s，。？！、]+", query) if len(kw) >= 2][:8]
    if not keywords:
        return []

    candidates = []
    scanned = 0
    scan_dirs = ([USERS_DIR / user_id] if user_id != "default" else MEMORY_SCAN_DIRS)
    for scan_dir in scan_dirs:
        if not scan_dir.exists() or scanned >= max_scan_files:
            continue
        for md_file in scan_dir.rglob("*.md"):
            if scanned >= max_scan_files:
                break
            scanned += 1

            try:
                if md_file.stat().st_size > 300_000:
                    continue
                rel = md_file.relative_to(META_AGENT_DIR)
                if str(rel).startswith("memory/tiered/"):
                    continue
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            score, signals = _compute_rerank_score(text, keywords)
            if signals["keyword_score"] <= 0:
                continue

            lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("---")]
            snippet = lines[0][:120] if lines else ""
            candidates.append(
                {
                    "path": str(rel),
                    "title": _extract_title(text),
                    "score": round(score, 2),
                    "signals": signals,
                    "snippet": snippet,
                }
            )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def _assess_ingest_risk(content: str, mem_type: str, title: str) -> dict:
    lowered = f"{title}\n{content}".lower()
    matched_keywords = sorted([kw for kw in RISKY_KEYWORDS if kw in lowered])

    reasons = []
    if mem_type in RISKY_TYPES:
        reasons.append(f"mem_type={mem_type}")
    if matched_keywords:
        reasons.append(f"keywords={','.join(matched_keywords[:6])}")
    if len(content) > 2500:
        reasons.append("large_payload")

    requires_approval = bool(reasons)
    risk_level = "high" if requires_approval else "low"
    return {
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "reasons": reasons,
    }


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

                # 更新 usage_count（每次命中 +1）
                usage_match = re.search(r"usage_count:\s*(\d+)", text)
                if usage_match:
                    old_usage = int(usage_match.group(1))
                    text = re.sub(r"usage_count:\s*\d+", f"usage_count: {old_usage + 1}", text)
                elif "last_triggered:" in text:
                    text = re.sub(
                        r"(last_triggered:\s*\S+)",
                        r"\1\nusage_count: 1",
                        text,
                        count=1,
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
async def query_memory(q: str, mode: str = "hybrid", user_id: str = "default") -> str:
    """
    語意搜尋 LightRAG 知識圖譜。

    Args:
        q: 搜尋查詢（中英文均可）
        mode: 搜尋模式 hybrid / local / global / naive（預設 hybrid）
        user_id: 用戶隔離 ID（預設 default = 不隔離）

    Returns:
        搜尋結果文字
    """
    payload = await query_memory_structured(q=q, mode=mode, user_id=user_id)
    result = payload["result"]
    updated = int(payload.get("memory_boost_updated", 0))
    reranked = payload.get("rerank_candidates", [])

    boost_note = f"\n[記憶強化：{updated} 個相關文件 last_triggered/usage_count 已更新]" if updated > 0 else ""
    rerank_note = ""
    if reranked:
        lines = ["", "[Local Rerank Top-3]"]
        for idx, item in enumerate(reranked, start=1):
            lines.append(
                f"{idx}. {item['title']} | score={item['score']} | conf={item['signals']['confidence']}"
                f" | freshness={item['signals']['freshness_score']} | usage={item['signals']['usage_count']}"
                f" | src={item['path']}"
            )
        rerank_note = "\n".join(lines)

    return f"[LightRAG {payload['mode']}]\n{result}{boost_note}{rerank_note}"


async def query_memory_structured(q: str, mode: str = "hybrid", user_id: str = "default") -> dict:
    """D5-4: 結構化查詢結果，提供 rerank_candidates 供 HTTP API 直接輸出 JSON 欄位。"""
    if mode not in ("hybrid", "local", "global", "naive"):
        mode = "hybrid"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{LIGHTRAG_API}/query",
            json={"query": q, "mode": mode},
        )
        resp.raise_for_status()
        data = resp.json()

    result = data.get("response") or data.get("result") or str(data)
    updated = _update_last_triggered(q)
    reranked = _local_rerank_candidates(q, limit=3, user_id=user_id)
    return {
        "result": result,
        "mode": mode,
        "query": q,
        "user_id": user_id,
        "memory_boost_updated": updated,
        "rerank_candidates": reranked,
    }


# ── 工具 2：ingest_memory ─────────────────────────────────────────────
@mcp.tool()
async def ingest_memory(content: str, mem_type: str = "verified_truth", title: str = "", user_id: str = "default") -> str:
    """
    將知識存入 LightRAG 圖譜（附 frontmatter）。

    Args:
        content: 知識內容（<3000字，法典禁止超過 4000）
        mem_type: 類型 error_fix / tech_decision / verified_truth / rule
        title: 簡短標題（選填）
        user_id: 用戶隔離 ID（預設 default = 共用圖譜，非預設另存本地副本）

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

    approved = content.startswith("[APPROVED]")
    confirmed = content.startswith("[CONFIRMED]") or approved

    # D5：寫入安全閘（高風險類型/關鍵詞需先審批）
    risk = _assess_ingest_risk(content=content, mem_type=mem_type, title=title)
    if risk["requires_approval"] and not approved:
        return (
            "⏳ ingest 需審批（risk=high）\n"
            f"原因：{'; '.join(risk['reasons'])}\n"
            "請在 content 開頭加入 [APPROVED] 後重試。"
        )

    # P4-A：矛盾檢查 — ingest 前先驗證
    # [CONFIRMED]/[APPROVED] 標記可跳過檢查（使用者已確認）
    if not confirmed:
        conflict_warning = _check_conflicts(content, title or content[:80])
        if conflict_warning:
            return conflict_warning

    today = date.today().isoformat()
    content_clean = re.sub(r"^\[(CONFIRMED|APPROVED)\]", "", content).strip()
    title = title or content_clean[:40].replace("\n", " ")
    expires = {"error_fix": 365, "tech_decision": 730, "rule": 180}.get(mem_type, 365)

    doc = (
        f"---\n"
        f"date: {today}\n"
        f"type: {mem_type}\n"
        f"status: active\n"
        f"last_triggered: {today}\n"
        f"usage_count: 0\n"
        f"confidence: 0.85\n"
        f"user_id: {user_id}\n"
        f"expires_after_days: {expires}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content_clean}\n"
    )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{LIGHTRAG_API}/documents/text",
            json={"text": doc, "description": title},
        )
        resp.raise_for_status()
        data = resp.json()

    # 多租戶：非預設用戶在本地保存隔離副本
    if user_id != "default":
        user_dir = USERS_DIR / re.sub(r"[^\w\-]", "_", user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^\w\-]", "-", title[:40].lower()).strip("-") or "untitled"
        local_file = user_dir / f"{today}-{slug}.md"
        local_file.write_text(doc, encoding="utf-8")

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

    # ingest 到 LightRAG（原始版本）—— [APPROVED] 跳過安全閘 + 矛盾檢查（log_error 永遠是蓄意的）
    ingest_result = await ingest_memory(
        content=f"[APPROVED]根因：{root_cause}\n解法：{solution}\n{context}",
        mem_type="error_fix",
        title=f"Error Fix: {root_cause[:50]}",
    )

    # Workflow C：fire-and-forget → Groq 結構化 + ingest 豐富版（不等回應）
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(
                ERROR_ARCHIVE_WEBHOOK,
                json={
                    "root_cause": root_cause,
                    "solution": solution,
                    "topic": safe_topic,
                    "context": context,
                    "filepath": str(filepath),
                },
            )
    except Exception:
        pass  # fire-and-forget，失敗不影響主流程

    return f"✅ 已寫入 {filepath}\n{ingest_result}\n[Workflow C 已觸發]"


# ── 入口 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"
ERROR_LOG_DIR = BASE_DIR / "error-log"
TRUTH_SOURCE_DIR = BASE_DIR / "truth-source"

STACKEXCHANGE_API = "https://api.stackexchange.com/2.3/search/advanced"
GITHUB_ISSUES_API = "https://api.github.com/search/issues"
BRAVE_SEARCH_API = "https://api.search.brave.com/res/v1/web/search"

# Domain/platform keyword mapping for official-doc-first retrieval.
OFFICIAL_DOC_SITES: dict[str, list[str]] = {
    "dify": ["docs.dify.ai"],
    "fastapi": ["fastapi.tiangolo.com"],
    "python": ["docs.python.org"],
    "docker": ["docs.docker.com"],
    "kubernetes": ["kubernetes.io/docs"],
    "n8n": ["docs.n8n.io"],
    "postgresql": ["postgresql.org/docs"],
    "redis": ["redis.io/docs"],
    "node": ["nodejs.org/docs"],
    "react": ["react.dev"],
    "next": ["nextjs.org/docs"],
    "yt-dlp": ["github.com/yt-dlp/yt-dlp"],
    "instaloader": ["instaloader.github.io", "github.com/instaloader/instaloader"],
}


@dataclass
class Evidence:
    source: str
    title: str
    snippet: str
    ref: str
    score: float
    category: str = "unknown"


def _load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


def _tokens(text: str) -> set[str]:
    # Keep English words, numbers, and CJK chunks.
    parts = re.findall(r"[A-Za-z0-9_./:-]+|[\u4e00-\u9fff]{2,}", (text or "").lower())
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "python",
        "error",
        "問題",
        "錯誤",
        "如何",
        "怎麼",
    }
    return {p for p in parts if p not in stop and len(p) > 1}


def _overlap_score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    t = _tokens(text)
    hit = len(query_tokens & t)
    return round(hit / max(1, len(query_tokens)), 4)


def _search_local_markdown(problem: str, max_items: int = 6) -> list[Evidence]:
    q_tokens = _tokens(problem)
    candidates: list[Evidence] = []

    for root, source_name in [(ERROR_LOG_DIR, "error-log"), (TRUTH_SOURCE_DIR, "truth-source")]:
        if not root.exists():
            continue
        for p in sorted(root.glob("*.md")):
            if p.name == "decision-template.md":
                continue
            text = p.read_text(encoding="utf-8")
            score = _overlap_score(q_tokens, text)
            if score <= 0:
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            snippet = " ".join(lines[:6])[:280]
            candidates.append(
                Evidence(
                    source=source_name,
                    title=p.name,
                    snippet=snippet,
                    ref=str(p.relative_to(BASE_DIR)),
                    score=score,
                )
            )

    candidates.sort(key=lambda x: x.score, reverse=True)
    return candidates[:max_items]


def _search_stackoverflow(problem: str, max_items: int = 5) -> list[Evidence]:
    params = {
        "order": "desc",
        "sort": "votes",
        "site": "stackoverflow",
        "q": problem,
        "accepted": "True",
        "pagesize": str(max(1, min(10, max_items))),
    }
    try:
        res = requests.get(STACKEXCHANGE_API, params=params, timeout=20)
        if res.status_code != 200:
            return []
        data = res.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        out: list[Evidence] = []
        q_tokens = _tokens(problem)
        for item in items:
            title = item.get("title", "")
            link = item.get("link", "")
            tags = ",".join(item.get("tags", []) or [])
            score_raw = float(item.get("score", 0) or 0)
            view_count = float(item.get("view_count", 0) or 0)
            text = f"{title} {tags}"
            lexical = _overlap_score(q_tokens, text)
            quality = min(1.0, (score_raw / 50.0) + (view_count / 200000.0))
            score = round((0.6 * lexical) + (0.4 * quality), 4)
            out.append(
                Evidence(
                    source="stackoverflow",
                    title=title,
                    snippet=f"tags={tags}; score={int(score_raw)}; views={int(view_count)}",
                    ref=link,
                    score=score,
                    category="forum",
                )
            )
        out.sort(key=lambda x: x.score, reverse=True)
        return out[:max_items]
    except Exception:
        return []


def _search_github_issues(problem: str, max_items: int = 5) -> list[Evidence]:
    params = {
        "q": f"{problem} is:issue state:open",
        "sort": "comments",
        "order": "desc",
        "per_page": str(max(1, min(10, max_items))),
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        res = requests.get(GITHUB_ISSUES_API, params=params, headers=headers, timeout=20)
        if res.status_code != 200:
            return []
        data = res.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        q_tokens = _tokens(problem)
        out: list[Evidence] = []
        for item in items:
            title = item.get("title", "")
            body = item.get("body", "") or ""
            link = item.get("html_url", "")
            comments = float(item.get("comments", 0) or 0)
            score_raw = float(item.get("score", 0) or 0)
            lexical = _overlap_score(q_tokens, f"{title} {body[:2000]}")
            quality = min(1.0, (comments / 20.0) + (score_raw / 100.0))
            score = round((0.65 * lexical) + (0.35 * quality), 4)
            out.append(
                Evidence(
                    source="github-issues",
                    title=title,
                    snippet=f"comments={int(comments)}; score={round(score_raw,2)}",
                    ref=link,
                    score=score,
                    category="bug_db",
                )
            )
        out.sort(key=lambda x: x.score, reverse=True)
        return out[:max_items]
    except Exception:
        return []


def _classify_web_category(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if any(x in host for x in ["github.com", "gitlab.com", "jira", "bugs.", "youtrack"]):
        return "bug_db"
    if any(x in host for x in ["stackoverflow.com", "reddit.com", "discuss", "forum", "community"]):
        return "forum"
    if any(x in host for x in ["docs.", "developer.", "readthedocs", "python.org", "fastapi.tiangolo.com"]):
        return "official_docs"
    return "other"


def _search_brave_web(problem: str, max_items: int = 6) -> list[Evidence]:
    _load_env_file()
    api_key = os.getenv("BRAVE_API_KEY", "").strip()
    if not api_key:
        return []
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": problem,
        "count": str(max(1, min(10, max_items))),
    }
    try:
        res = requests.get(BRAVE_SEARCH_API, headers=headers, params=params, timeout=20)
        if res.status_code != 200:
            return []
        data = res.json()
        web = (data.get("web") or {}).get("results") or []
        q_tokens = _tokens(problem)
        out: list[Evidence] = []
        for item in web:
            title = item.get("title", "")
            desc = item.get("description", "")
            link = item.get("url", "")
            category = _classify_web_category(link)
            lexical = _overlap_score(q_tokens, f"{title} {desc}")
            boost = 0.15 if category in {"official_docs", "bug_db", "forum"} else 0.0
            score = round(min(1.0, lexical + boost), 4)
            out.append(
                Evidence(
                    source="brave-web",
                    title=title,
                    snippet=desc[:280],
                    ref=link,
                    score=score,
                    category=category,
                )
            )
        out.sort(key=lambda x: x.score, reverse=True)
        return out[:max_items]
    except Exception:
        return []


def _platform_doc_queries(problem: str) -> list[str]:
    p = (problem or "").lower()
    tokens = _tokens(p)
    targets: list[str] = []

    for key, sites in OFFICIAL_DOC_SITES.items():
        if key in p or key in tokens:
            targets.extend(sites)

    # Generic fallback when no platform keyword detected.
    if not targets:
        return [f"{problem} official documentation"]

    # Build site-scoped doc queries.
    return [f"{problem} site:{site}" for site in targets]


def _search_official_docs_first(problem: str, max_items: int = 6) -> list[Evidence]:
    queries = _platform_doc_queries(problem)
    merged: list[Evidence] = []
    for q in queries[:4]:
        for e in _search_brave_web(q, max_items=max_items):
            if e.category == "official_docs":
                # Official docs get a relevance boost by policy.
                e.score = round(min(1.0, e.score + 0.2), 4)
                merged.append(e)

    # de-dup by URL
    uniq: dict[str, Evidence] = {}
    for e in merged:
        if e.ref not in uniq or uniq[e.ref].score < e.score:
            uniq[e.ref] = e

    out = sorted(uniq.values(), key=lambda x: x.score, reverse=True)
    return out[:max_items]


def _build_solution_paths(problem: str, evidences: list[Evidence], top_k: int = 3) -> list[dict[str, Any]]:
    # Build diverse paths by source-first grouping.
    paths: list[dict[str, Any]] = []
    local = [e for e in evidences if e.source in {"error-log", "truth-source"}]
    so = [e for e in evidences if e.source == "stackoverflow"]
    gh = [e for e in evidences if e.source == "github-issues"]
    docs = [e for e in evidences if e.category == "official_docs"]
    forum = [e for e in evidences if e.category == "forum"]
    bugdb = [e for e in evidences if e.category == "bug_db"]

    if docs:
        paths.append(
            {
                "name": "D: 官方文件對齊",
                "rationale": "先對齊對應平台官方文件，確認正確配置與預期行為。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in docs[:2]
                ],
                "risk": "low",
            }
        )

    if local:
        paths.append(
            {
                "name": "A: 沿用本地既有修復模式",
                "rationale": "優先沿用你這個 repo 已驗證過的修復策略，回歸風險最低。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in local[:2]
                ],
                "risk": "low",
            }
        )

        # Even without external hits, keep multiple debug routes for comparison.
        paths.append(
            {
                "name": "B: 觀測先行（timeout/403 分離）",
                "rationale": "先把 timeout 與 403 分開觀測，補 request id、上游狀態碼、重試次數，縮小根因範圍。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in local[1:3]
                ],
                "risk": "low",
            }
        )

        paths.append(
            {
                "name": "C: 先做最小防禦修補",
                "rationale": "先加 timeout budget、retry/backoff、降級 fallback，先恢復可用性再回頭做根因修復。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in local[:1]
                ],
                "risk": "low-medium",
            }
        )

    if so:
        paths.append(
            {
                "name": "B: 參考社群高票解法",
                "rationale": "導入 Stack Overflow 已採納/高票方案，擴大候選解法空間。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in so[:2]
                ],
                "risk": "medium",
            }
        )

    if local and so:
        paths.append(
            {
                "name": "C: 混合策略（本地保守 + 社群增量）",
                "rationale": "先套本地穩定修復，再用社群解法做最小增量優化。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in (local[:1] + so[:1])
                ],
                "risk": "low-medium",
            }
        )

    if gh or bugdb:
        picks = (gh[:1] + bugdb[:1])[:2]
        paths.append(
            {
                "name": "E: Bug 庫已知問題路線",
                "rationale": "先比對是否是已知 issue，再決定 workaround 或版本升級。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in picks
                ],
                "risk": "medium",
            }
        )

    if forum and not so:
        paths.append(
            {
                "name": "F: 論壇經驗比對",
                "rationale": "用社群討論補齊邊角案例，再回到本地驗證。",
                "evidence": [
                    {"source": e.source, "title": e.title, "ref": e.ref, "score": e.score}
                    for e in forum[:2]
                ],
                "risk": "medium",
            }
        )

    if not paths:
        paths.append(
            {
                "name": "Fallback: 最小重現先行",
                "rationale": "暫無高信號來源，先縮小問題範圍與重現步驟。",
                "evidence": [],
                "risk": "unknown",
            }
        )

    deduped: list[dict[str, Any]] = []
    seen = set()
    for p in paths:
        name = p.get("name")
        if name in seen:
            continue
        seen.add(name)
        deduped.append(p)
    return deduped[: max(1, top_k)]


def generate_debug_solutions(problem: str, top_k: int = 3) -> dict[str, Any]:
    if not problem or not problem.strip():
        raise ValueError("problem is required")

    official = _search_official_docs_first(problem, max_items=6)
    local = _search_local_markdown(problem, max_items=6)
    so = _search_stackoverflow(problem, max_items=5)
    gh = _search_github_issues(problem, max_items=5)
    web = _search_brave_web(problem, max_items=6)
    merged = sorted(official + local + so + gh + web, key=lambda x: x.score, reverse=True)
    paths = _build_solution_paths(problem=problem, evidences=merged, top_k=top_k)

    return {
        "ok": True,
        "problem": problem,
        "doc_priority_applied": True,
        "summary": {
            "official_doc_hits": len(official),
            "local_hits": len(local),
            "stackoverflow_hits": len(so),
            "github_issue_hits": len(gh),
            "web_hits": len(web),
            "total_evidence": len(merged),
            "paths": len(paths),
        },
        "paths": paths,
        "top_evidence": [
            {
                "source": e.source,
                "title": e.title,
                "snippet": e.snippet,
                "ref": e.ref,
                "score": e.score,
                "category": e.category,
            }
            for e in merged[:8]
        ],
    }


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)

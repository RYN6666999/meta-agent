from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import requests

from common.instagram_extract import extract_instagram_post

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("IG_DISCUSS_MODEL", "google/gemini-2.0-flash-001")
LIGHTRAG_API = os.getenv("LIGHTRAG_API", "http://localhost:9621")
TRUTH_SOURCE_DIR = BASE_DIR / "truth-source"


def _run_git(args: list[str]) -> tuple[str, int]:
    result = subprocess.run(
        ["git"] + args,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.returncode


def _git_branch_exists(branch_name: str) -> bool:
    stdout, _ = _run_git(["branch", "--list", branch_name])
    return bool(stdout.strip())


def _lightrag_health() -> bool:
    try:
        with urllib.request.urlopen(f"{LIGHTRAG_API}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _parse_frontmatter_branch(text: str) -> str:
    # Only parse a simple frontmatter branch key.
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    block = text[3:end].splitlines()
    for line in block:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "branch":
            return value.strip()
    return ""


def truth_source_cross_check() -> dict[str, Any]:
    files = sorted(p for p in TRUTH_SOURCE_DIR.glob("*.md") if p.name != "decision-template.md")
    details: list[dict[str, Any]] = []
    git_branch_errors = 0
    with_branch = 0

    for p in files:
        text = p.read_text(encoding="utf-8")
        branch = _parse_frontmatter_branch(text)
        branch_ok = None
        if branch:
            with_branch += 1
            branch_ok = _git_branch_exists(branch)
            if not branch_ok:
                git_branch_errors += 1
        details.append(
            {
                "file": p.name,
                "branch": branch,
                "git_branch_ok": branch_ok,
            }
        )

    lightrag_ok = _lightrag_health()
    passed = len(files) > 0 and git_branch_errors == 0

    return {
        "passed": passed,
        "total_truth_files": len(files),
        "files_with_branch": with_branch,
        "git_branch_errors": git_branch_errors,
        "lightrag_available": lightrag_ok,
        "details": details[:20],
    }


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


def _openrouter_chat(messages: list[dict[str, Any]], max_tokens: int = 1200, temperature: float = 0.1) -> str:
    _load_env_file()
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("missing_openrouter_api_key")

    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    res = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    if res.status_code != 200:
        raise RuntimeError(f"openrouter_http_{res.status_code}: {(res.text or '')[:300]}")
    data = res.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def _ocr_image_raw(image_url: str) -> str:
    prompt = (
        "你是OCR引擎。請只做文字辨識，規則如下：\n"
        "1) 僅輸出圖片中可見文字，不要摘要、不要翻譯、不要改寫。\n"
        "2) 盡量保留原本行序與換行。\n"
        "3) 看不清楚的字請以 [UNREADABLE] 標記。\n"
        "4) 只輸出純文字，不要 JSON，不要 Markdown，不要解釋。"
    )
    content = _openrouter_chat(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        max_tokens=1200,
        temperature=0,
    )
    return content.strip()


def _is_handle_line(line: str) -> bool:
    return re.match(r"^@[a-zA-Z0-9._]+$", line.strip()) is not None


def _is_brand_line(line: str) -> bool:
    s = line.strip().lower()
    brand_keywords = ["boss財道", "修行智慧", "take away", "@boss.fdao"]
    return any(k in s for k in brand_keywords)


def _is_cta_line(line: str) -> bool:
    s = line.strip().lower()
    cta_keywords = [
        "想了解更多",
        "加入",
        "訂閱",
        "獲得",
        "優先獲取",
        "連結在個人簡介",
        "patreon",
    ]
    return any(k in s for k in cta_keywords)


def _is_promo_list_line(line: str) -> bool:
    s = line.strip()
    return s.startswith(">>") or s.startswith("→")


def _is_url_line(line: str) -> bool:
    s = line.strip().lower()
    return s.startswith("http://") or s.startswith("https://") or "patreon.com" in s


def clean_ocr_text(raw_text: str) -> str:
    lines = [ln.rstrip() for ln in (raw_text or "").splitlines()]
    cleaned: list[str] = []
    in_promo_block = False

    for line in lines:
        s = line.strip()
        if not s:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            in_promo_block = False
            continue

        if _is_handle_line(s):
            continue

        if _is_cta_line(s):
            in_promo_block = True
            continue

        if in_promo_block and (_is_promo_list_line(s) or _is_url_line(s) or _is_brand_line(s)):
            continue

        if _is_brand_line(s):
            continue

        cleaned.append(s)

    deduped: list[str] = []
    seen: set[str] = set()
    for ln in cleaned:
        key = re.sub(r"\s+", " ", ln).strip().lower()
        if not key:
            if deduped and deduped[-1] != "":
                deduped.append("")
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ln)

    while deduped and deduped[-1] == "":
        deduped.pop()

    return "\n".join(deduped).strip()


def prepare_instagram_discussion(url: str, remove_promo: bool = True, max_images: int = 9) -> dict[str, Any]:
    post = extract_instagram_post(url)
    images = [m.get("url") for m in post.get("media", []) if m.get("type") == "image" and isinstance(m.get("url"), str)]
    images = images[: max(1, max_images)]

    ocr_items: list[dict[str, Any]] = []
    for i, image_url in enumerate(images, start=1):
        try:
            raw = _ocr_image_raw(image_url)
            cleaned = clean_ocr_text(raw) if remove_promo else raw
            ocr_items.append(
                {
                    "index": i,
                    "image_url": image_url,
                    "raw_ocr": raw,
                    "cleaned_ocr": cleaned,
                    "ok": True,
                }
            )
        except Exception as exc:
            ocr_items.append(
                {
                    "index": i,
                    "image_url": image_url,
                    "ok": False,
                    "error": str(exc)[:300],
                }
            )

    combined_cleaned = "\n\n".join(
        f"[圖{i['index']}]\n{i.get('cleaned_ocr', '')}" for i in ocr_items if i.get("ok") and i.get("cleaned_ocr")
    ).strip()

    return {
        "ok": True,
        "url": url,
        "author": post.get("author"),
        "caption": post.get("caption") or "",
        "media_count": post.get("media_count"),
        "ocr_count": len(ocr_items),
        "remove_promo": remove_promo,
        "combined_cleaned_text": combined_cleaned,
        "items": ocr_items,
    }


def discuss_instagram_post(url: str, question: str, remove_promo: bool = True, max_images: int = 9) -> dict[str, Any]:
    if not question or not question.strip():
        raise ValueError("question is required")

    truth_guard = truth_source_cross_check()
    if not truth_guard.get("passed"):
        return {
            "ok": False,
            "error": "truth_guard_failed",
            "message": "回答前真理源交叉比對未通過，已停止回答。",
            "truth_guard": truth_guard,
        }

    prepared = prepare_instagram_discussion(url=url, remove_promo=remove_promo, max_images=max_images)
    context_text = prepared.get("combined_cleaned_text", "")
    caption = prepared.get("caption", "")

    answer = _openrouter_chat(
        messages=[
            {
                "role": "system",
                "content": "你是貼文內容分析助手。只能根據提供的 caption 與 OCR 內容回答；若證據不足要明確說不知道。",
            },
            {
                "role": "user",
                "content": (
                    f"IG URL: {url}\n\n"
                    f"Caption:\n{caption}\n\n"
                    f"OCR(cleaned):\n{context_text}\n\n"
                    f"問題: {question}\n\n"
                    "請用繁體中文回答，並附上你引用到的關鍵句(可多條)。"
                ),
            },
        ],
        max_tokens=900,
        temperature=0.2,
    ).strip()

    return {
        "ok": True,
        "url": url,
        "question": question,
        "answer": answer,
        "truth_guard": truth_guard,
        "evidence_source": {
            "caption_len": len(caption),
            "combined_cleaned_text_len": len(context_text),
            "ocr_count": prepared.get("ocr_count", 0),
        },
    }


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)

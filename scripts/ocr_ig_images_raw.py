from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from common.instagram_extract import extract_instagram_post


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


def ocr_image_raw(api_key: str, image_url: str) -> dict:
    # Strict OCR prompt: no summary, no translation, no rewriting.
    prompt = (
        "你是OCR引擎。請只做文字辨識，規則如下：\n"
        "1) 僅輸出圖片中可見文字，不要摘要、不要翻譯、不要改寫。\n"
        "2) 盡量保留原本行序與換行。\n"
        "3) 看不清楚的字請以 [UNREADABLE] 標記。\n"
        "4) 只輸出純文字，不要 JSON，不要 Markdown，不要解釋。"
    )
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 900,
    }
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    if res.status_code != 200:
        return {
            "ok": False,
            "status_code": res.status_code,
            "error": (res.text or "")[:800],
        }
    data = res.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {
        "ok": True,
        "ocr_text": content,
    }


def main() -> None:
    load_env_file(REPO_DIR / ".env")
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"ok": False, "error": "missing_openrouter_api_key"}, ensure_ascii=False, indent=2))
        return

    url = sys.argv[1].strip() if len(sys.argv) > 1 else "https://www.instagram.com/p/DVqFtTlkY2a/"
    out_file = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) > 2
        else (REPO_DIR / "memory" / "ig-ocr-raw-latest.json")
    )

    post = extract_instagram_post(url)
    images = [m.get("url") for m in post.get("media", []) if m.get("type") == "image" and isinstance(m.get("url"), str)]

    result = {
        "ok": True,
        "url": url,
        "author": post.get("author"),
        "media_count": post.get("media_count"),
        "image_count_for_ocr": len(images),
        "items": [],
    }

    for i, image_url in enumerate(images, start=1):
        ocr = ocr_image_raw(api_key=api_key, image_url=image_url)
        result["items"].append(
            {
                "index": i,
                "image_url": image_url,
                **ocr,
            }
        )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_file))


if __name__ == "__main__":
    main()

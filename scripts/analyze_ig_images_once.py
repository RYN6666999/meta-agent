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


def analyze_image(api_key: str, image_url: str) -> dict:
    prompt = (
        "你是內容分析助手。請根據這張圖輸出 JSON，欄位為: "
        "scene, key_objects(array), text_in_image, tone, marketing_angle, risk_flags(array)。"
        "請用繁體中文，精簡且具體。"
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
        "temperature": 0.2,
        "max_tokens": 500,
    }
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    if res.status_code != 200:
        return {
            "ok": False,
            "status_code": res.status_code,
            "error": (res.text or "")[:500],
        }
    data = res.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {
        "ok": True,
        "analysis_raw": content,
    }


def main() -> None:
    load_env_file(Path(".env"))
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"ok": False, "error": "missing_openrouter_api_key"}, ensure_ascii=False, indent=2))
        return

    url = "https://www.instagram.com/p/DVqFtTlkY2a/"
    post = extract_instagram_post(url)
    images = [m.get("url") for m in post.get("media", []) if m.get("type") == "image"][:3]

    output = {
        "ok": True,
        "post": {
            "url": url,
            "author": post.get("author"),
            "caption_preview": (post.get("caption") or "")[:120],
            "media_count": post.get("media_count"),
            "cache_hit": post.get("cache_hit"),
            "elapsed_ms": post.get("elapsed_ms"),
        },
        "image_analysis": [],
    }

    for i, image_url in enumerate(images, start=1):
        result = analyze_image(api_key=api_key, image_url=image_url)
        output["image_analysis"].append(
            {
                "index": i,
                "image_url_preview": (image_url or "")[:120],
                **result,
            }
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

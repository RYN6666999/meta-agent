from __future__ import annotations

import json
import os
import subprocess
import importlib
import re
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None

from common.jsonio import load_json, save_json

YT_DLP_BIN = os.getenv("YT_DLP_BIN", "yt-dlp")
YT_DLP_TIMEOUT_SEC = int(os.getenv("YT_DLP_TIMEOUT_SEC", "45"))
YT_DLP_COOKIE_BROWSERS = [
    b.strip() for b in os.getenv("IG_YTDLP_COOKIE_BROWSERS", "safari,chrome").split(",") if b.strip()
]
INSTALOADER_TIMEOUT_SEC = int(os.getenv("IG_INSTALOADER_TIMEOUT_SEC", "45"))
INSTALOADER_MAX_CONNECTION_ATTEMPTS = int(os.getenv("IG_INSTALOADER_MAX_CONNECTION_ATTEMPTS", "2"))
INSTALOADER_USER = os.getenv("IG_INSTALOADER_USERNAME", "").strip()
INSTALOADER_SESSIONFILE = os.getenv("IG_INSTALOADER_SESSIONFILE", "").strip()
JSONLD_TIMEOUT_SEC = int(os.getenv("IG_JSONLD_TIMEOUT_SEC", "15"))
IG_ENABLE_JSONLD_FALLBACK = os.getenv("IG_ENABLE_JSONLD_FALLBACK", "1") == "1"

BASE_DIR = Path(__file__).resolve().parents[1]
IG_CACHE_FILE = Path(os.getenv("IG_EXTRACT_CACHE_FILE", str(BASE_DIR / "memory" / "ig-extract-cache.json")))
IG_CACHE_TTL_SEC = int(os.getenv("IG_EXTRACT_CACHE_TTL_SEC", "900"))
IG_ALLOW_STALE_CACHE_ON_FAILURE = os.getenv("IG_ALLOW_STALE_CACHE_ON_FAILURE", "1") == "1"


def _extract_first_instagram_url(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/[^\s)]+", text, flags=re.IGNORECASE)
    return match.group(0).strip() if match else None


def _classify_error(message: str) -> str:
    msg = (message or "").lower()
    if any(x in msg for x in ["timed out", "timeout", "connection", "dns", "name or service not known"]):
        return "network"
    if any(x in msg for x in ["login", "401", "403", "permission", "private", "challenge", "checkpoint"]):
        return "auth"
    if any(x in msg for x in ["unsupported", "invalid", "shortcode", "only supports"]):
        return "format"
    if any(x in msg for x in ["429", "rate", "blocked", "captcha", "turnstile"]):
        return "provider_block"
    return "unknown"


def _validate_instagram_url(url: str) -> None:
    parsed = urlparse((url or "").strip())
    host = parsed.netloc.lower()
    if "instagram.com" not in host and "instagr.am" not in host:
        raise ValueError("只支援 instagram.com / instagr.am 網址")


def _extract_shortcode(url: str) -> str:
    path_parts = [p for p in urlparse(url).path.split("/") if p]
    # Supported paths: /p/<shortcode>/, /reel/<shortcode>/, /tv/<shortcode>/
    if len(path_parts) >= 2 and path_parts[0] in {"p", "reel", "tv"}:
        return path_parts[1]
    raise ValueError("無法從 URL 解析 shortcode")


def _normalize_instagram_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = parsed.netloc.lower()
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) >= 2 and path_parts[0] in {"p", "reel", "tv"}:
        return f"https://www.instagram.com/{path_parts[0]}/{path_parts[1]}/"
    # fallback: return original normalized without query/fragment
    return f"https://{host}{parsed.path}"


def _cache_key(url: str) -> str:
    try:
        return _extract_shortcode(url)
    except Exception:
        return _normalize_instagram_url(url)


def _load_cache() -> dict:
    data = load_json(IG_CACHE_FILE, {"version": 1, "items": {}})
    if not isinstance(data, dict):
        return {"version": 1, "items": {}}
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return data


def _cache_get(url: str) -> dict | None:
    data = _load_cache()
    item = data["items"].get(_cache_key(url))
    if not isinstance(item, dict):
        return None
    cached_at = int(item.get("cached_at", 0) or 0)
    if cached_at <= 0 or (int(time.time()) - cached_at) > IG_CACHE_TTL_SEC:
        return None
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return None
    # Return a shallow copy so caller can append attempts without mutating cache.
    return dict(payload)


def _cache_get_stale(url: str) -> dict | None:
    data = _load_cache()
    item = data["items"].get(_cache_key(url))
    if not isinstance(item, dict):
        return None
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def _cache_put(url: str, payload: dict) -> None:
    data = _load_cache()
    data["items"][_cache_key(url)] = {
        "cached_at": int(time.time()),
        "payload": payload,
    }
    save_json(IG_CACHE_FILE, data)


def _collect_media_urls(item: dict) -> list[dict]:
    media: list[dict] = []
    seen: set[str] = set()

    def add(url: str, media_type: str, width: int | None = None, height: int | None = None) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        media.append(
            {
                "type": media_type,
                "url": url,
                "width": width,
                "height": height,
            }
        )

    is_video = bool(item.get("is_video") or item.get("vcodec") not in (None, "none"))
    media_type = "video" if is_video else "image"

    main_url = item.get("url")
    if isinstance(main_url, str):
        add(main_url, media_type, item.get("width"), item.get("height"))

    for thumb in item.get("thumbnails", []) or []:
        t_url = thumb.get("url")
        if isinstance(t_url, str):
            add(t_url, "image", thumb.get("width"), thumb.get("height"))

    thumbnail = item.get("thumbnail")
    if isinstance(thumbnail, str):
        add(thumbnail, "image")

    for fmt in item.get("formats", []) or []:
        f_url = fmt.get("url")
        if not isinstance(f_url, str):
            continue
        f_type = "video" if fmt.get("vcodec") not in (None, "none") else "image"
        add(f_url, f_type, fmt.get("width"), fmt.get("height"))

    return media


def _run_ytdlp(url: str, cookie_browser: str | None) -> dict:
    cmd = [
        YT_DLP_BIN,
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--ignore-no-formats-error",
        "--extractor-retries",
        "2",
        "--retries",
        "2",
    ]
    if cookie_browser:
        cmd.extend(["--cookies-from-browser", cookie_browser])
    cmd.append(url)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=YT_DLP_TIMEOUT_SEC,
        check=False,
    )

    stderr_tail = (proc.stderr or "").strip()[-500:]
    if not (proc.stdout or "").strip():
        raise RuntimeError(f"yt-dlp empty output(code={proc.returncode}): {stderr_tail}")

    data = json.loads((proc.stdout or "").strip())
    if not isinstance(data, dict):
        raise RuntimeError("yt-dlp output is not a dict")

    entries = data.get("entries") if isinstance(data.get("entries"), list) else None
    items = [x for x in entries if isinstance(x, dict)] if entries else [data]

    all_media: list[dict] = []
    for item in items:
        all_media.extend(_collect_media_urls(item))

    deduped: list[dict] = []
    seen_urls: set[str] = set()
    for m in all_media:
        u = m.get("url")
        if not isinstance(u, str) or u in seen_urls:
            continue
        seen_urls.add(u)
        deduped.append(m)

    caption = ""
    for key in ("description", "caption", "title"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            caption = val.strip()
            break

    return {
        "payload": {
            "source": "yt-dlp",
            "url": data.get("webpage_url") or url,
            "id": data.get("id"),
            "shortcode": data.get("display_id") or data.get("id"),
            "author": data.get("uploader") or data.get("channel"),
            "timestamp": data.get("timestamp"),
            "caption": caption,
            "media": deduped,
            "media_count": len(deduped),
            "raw_keys": sorted(list(data.keys()))[:40],
        },
        "meta": {
            "cookie_browser": cookie_browser,
            "returncode": proc.returncode,
            "stderr_tail": stderr_tail,
        },
    }


def _run_instaloader(url: str) -> dict:
    try:
        instaloader = importlib.import_module("instaloader")
    except Exception:
        instaloader = None

    if instaloader is None:
        raise RuntimeError("instaloader is not installed")

    shortcode = _extract_shortcode(url)
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_comments=False,
        save_metadata=False,
        quiet=True,
        max_connection_attempts=INSTALOADER_MAX_CONNECTION_ATTEMPTS,
        request_timeout=float(INSTALOADER_TIMEOUT_SEC),
    )

    if INSTALOADER_USER and INSTALOADER_SESSIONFILE:
        try:
            loader.load_session_from_file(INSTALOADER_USER, INSTALOADER_SESSIONFILE)
        except Exception:
            # Session file is optional. Ignore and continue as guest.
            pass

    post = instaloader.Post.from_shortcode(loader.context, shortcode)

    media: list[dict] = []
    if post.typename == "GraphSidecar":
        for node in post.get_sidecar_nodes():
            media.append(
                {
                    "type": "video" if node.is_video else "image",
                    "url": node.video_url if node.is_video else node.display_url,
                    "width": None,
                    "height": None,
                }
            )
    else:
        media.append(
            {
                "type": "video" if post.is_video else "image",
                "url": post.video_url if post.is_video else post.url,
                "width": None,
                "height": None,
            }
        )

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in media:
        u = item.get("url")
        if isinstance(u, str) and u not in seen:
            seen.add(u)
            deduped.append(item)

    return {
        "source": "instaloader",
        "url": url,
        "id": shortcode,
        "shortcode": shortcode,
        "author": post.owner_username,
        "timestamp": int(post.date_utc.timestamp()) if post.date_utc else None,
        "caption": post.caption or "",
        "media": deduped,
        "media_count": len(deduped),
        "raw_keys": ["typename", "is_video", "owner_username", "date_utc"],
    }


def _run_jsonld(url: str) -> dict:
    """
    直接爬取 IG 頁面的 JSON-LD schema，提取媒體與caption。
    用於當 yt-dlp 返回 media_count=0 但 caption 存在時的 fallback。
    """
    if not requests:
        raise RuntimeError("requests not installed for JSON-LD fallback")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        resp = requests.get(url, timeout=JSONLD_TIMEOUT_SEC, headers=headers, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch IG page: {str(exc)[:200]}")
    
    html = resp.text
    
    # 提取 JSON-LD schema (BreadcrumbList 或 ItemList 中通常有媒體信息)
    jsonld_pattern = r'<script type="application/ld\+json">([\s\S]*?)</script>'
    jsonld_matches = re.findall(jsonld_pattern, html)
    
    media: list[dict] = []
    caption = ""
    author = ""
    
    for match in jsonld_matches:
        try:
            data = json.loads(match)
            
            # 嘗試從不同的 schema 類型中提取信息
            if isinstance(data, dict):
                # Image 或 VideoObject
                if data.get("@type") == "ImageObject":
                    url_field = data.get("url") or data.get("contentUrl")
                    if isinstance(url_field, str) and url_field.startswith("http"):
                        media.append({"type": "image", "url": url_field, "width": None, "height": None})
                
                elif data.get("@type") == "VideoObject":
                    url_field = data.get("contentUrl") or data.get("url")
                    if isinstance(url_field, str) and url_field.startswith("http"):
                        media.append({"type": "video", "url": url_field, "width": None, "height": None})
                
                # Person (可能有 caption/description)
                if data.get("@type") == "Person":
                    author = data.get("name", "")
                
                # 多媒體陣列 (image/video 欄位)
                for img_list in [data.get("image"), data.get("images")]:
                    if isinstance(img_list, list):
                        for img_item in img_list:
                            if isinstance(img_item, str):
                                if img_item.startswith("http"):
                                    media.append({"type": "image", "url": img_item, "width": None, "height": None})
                            elif isinstance(img_item, dict):
                                img_url = img_item.get("url") or img_item.get("contentUrl")
                                if isinstance(img_url, str) and img_url.startswith("http"):
                                    media.append({"type": "image", "url": img_url, "width": None, "height": None})
                
                # caption/description
                for key in ["caption", "description", "text", "articleBody"]:
                    val = data.get(key)
                    if isinstance(val, str) and val.strip() and not caption:
                        caption = val.strip()
                        break
        
        except (json.JSONDecodeError, ValueError):
            continue
    
    # 也從 HTML meta tag 提取 og:image / og:video
    og_image_pattern = r'<meta\s+property="og:image"\s+content="([^"]+)"'
    og_video_pattern = r'<meta\s+property="og:video"\s+content="([^"]+)"'
    og_desc_pattern = r'<meta\s+property="og:description"\s+content="([^"]+)"'
    
    for match in re.findall(og_image_pattern, html):
        if match.startswith("http"):
            media.append({"type": "image", "url": match, "width": None, "height": None})
    
    for match in re.findall(og_video_pattern, html):
        if match.startswith("http"):
            media.append({"type": "video", "url": match, "width": None, "height": None})
    
    for match in re.findall(og_desc_pattern, html):
        if not caption:
            caption = match.strip()
    
    # 去重
    deduped: list[dict] = []
    seen_urls: set[str] = set()
    for m in media:
        u = m.get("url")
        if isinstance(u, str) and u not in seen_urls:
            seen_urls.add(u)
            deduped.append(m)
    
    try:
        shortcode = _extract_shortcode(url)
    except Exception:
        shortcode = ""
    
    return {
        "payload": {
            "source": "jsonld",
            "url": url,
            "id": shortcode,
            "shortcode": shortcode,
            "author": author,
            "timestamp": None,
            "caption": caption,
            "media": deduped,
            "media_count": len(deduped),
            "raw_keys": ["og:image", "og:video", "og:description"],
        },
        "meta": {
            "http_status": resp.status_code,
            "jsonld_schemas_found": len(jsonld_matches),
        },
    }


def extract_instagram_post(url: str) -> dict:
    started = time.perf_counter()
    extracted_url = _extract_first_instagram_url(url)
    if extracted_url:
        url = extracted_url
    _validate_instagram_url(url)
    normalized_url = _normalize_instagram_url(url)

    cached = _cache_get(normalized_url)
    if isinstance(cached, dict):
        cached["cache_hit"] = True
        cached["error_class"] = "none"
        cached["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        cached["attempts"] = [{"method": "cache", "ok": True, "media_count": cached.get("media_count", 0)}]
        return cached

    attempts: list[dict] = []
    candidates: list[str | None] = [None] + YT_DLP_COOKIE_BROWSERS
    last_payload = None
    last_error = ""

    for browser in candidates:
        try:
            out = _run_ytdlp(url=normalized_url, cookie_browser=browser)
            payload = out["payload"]
            attempts.append({"cookie_browser": browser, "ok": True, "media_count": payload["media_count"]})
            if payload["media_count"] > 0:
                payload["cache_hit"] = False
                payload["error_class"] = "none"
                payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                payload["attempts"] = attempts
                _cache_put(normalized_url, payload)
                return payload
            # yt-dlp 返回 0 個媒體，但可能有 caption - 嘗試 JSON-LD fallback
            if payload.get("caption", "").strip() and IG_ENABLE_JSONLD_FALLBACK:
                try:
                    out_jsonld = _run_jsonld(normalized_url)
                    jsonld_payload = out_jsonld["payload"]
                    attempts.append({"method": "jsonld", "ok": True, "media_count": jsonld_payload["media_count"]})
                    if jsonld_payload["media_count"] > 0:
                        jsonld_payload["cache_hit"] = False
                        jsonld_payload["error_class"] = "none"
                        jsonld_payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                        jsonld_payload["attempts"] = attempts
                        _cache_put(normalized_url, jsonld_payload)
                        return jsonld_payload
                except Exception as exc:
                    attempts.append({"method": "jsonld", "ok": False, "error": str(exc)[:200]})
            last_payload = payload
        except Exception as exc:
            attempts.append({"cookie_browser": browser, "ok": False, "error": str(exc)[:200]})
            last_error = str(exc)

    # fallback 2: instaloader (metadata + media extraction by shortcode)
    try:
        alt = _run_instaloader(normalized_url)
        attempts.append({"method": "instaloader", "ok": True, "media_count": alt["media_count"]})
        alt["cache_hit"] = False
        alt["error_class"] = "none"
        alt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        alt["attempts"] = attempts
        _cache_put(normalized_url, alt)
        return alt
    except Exception as exc:
        attempts.append({"method": "instaloader", "ok": False, "error": str(exc)[:200]})
        last_error = str(exc)

    # 最後嘗試 JSON-LD fallback（如果還沒試過）
    if IG_ENABLE_JSONLD_FALLBACK and not any(a.get("method") == "jsonld" for a in attempts):
        try:
            out_jsonld = _run_jsonld(normalized_url)
            jsonld_payload = out_jsonld["payload"]
            attempts.append({"method": "jsonld", "ok": True, "media_count": jsonld_payload["media_count"]})
            if jsonld_payload["media_count"] > 0:
                jsonld_payload["cache_hit"] = False
                jsonld_payload["error_class"] = "none"
                jsonld_payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                jsonld_payload["attempts"] = attempts
                _cache_put(normalized_url, jsonld_payload)
                return jsonld_payload
        except Exception as exc:
            attempts.append({"method": "jsonld", "ok": False, "error": str(exc)[:200]})
            last_error = str(exc)

    if isinstance(last_payload, dict):
        last_payload["cache_hit"] = False
        last_payload["error_class"] = _classify_error(last_error)
        last_payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        last_payload["attempts"] = attempts
        _cache_put(normalized_url, last_payload)
        return last_payload

    if IG_ALLOW_STALE_CACHE_ON_FAILURE:
        stale = _cache_get_stale(normalized_url)
        if isinstance(stale, dict):
            stale["cache_hit"] = True
            stale["stale_cache"] = True
            stale["error_class"] = _classify_error(last_error)
            stale["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            stale["attempts"] = attempts + [{"method": "stale_cache_fallback", "ok": True}]
            return stale

    raise RuntimeError(last_error or "yt-dlp extraction failed")

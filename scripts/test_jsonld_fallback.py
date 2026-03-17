#!/usr/bin/env python3
"""
Smoke test for JSON-LD fallback layer in Instagram extraction.
Tests 5 known IG posts across different types (single, carousel, reel).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from common.instagram_extract import extract_instagram_post

# Test cases: (url, expected_type, description)
TEST_CASES = [
    (
        "https://www.instagram.com/p/DB1qK_ByAcz/",
        "single_image",
        "Single image post (public account)"
    ),
    (
        "https://www.instagram.com/reel/DFTm_bUo7SR/",
        "reel",
        "Reel video post"
    ),
    (
        "https://www.instagram.com/p/DC7NUUVIhz9/",
        "carousel",
        "Carousel (multiple images)"
    ),
]

def main():
    print("=" * 80)
    print("JSON-LD Fallback Smoke Test")
    print("=" * 80)
    
    results = []
    
    for url, expected_type, description in TEST_CASES:
        print(f"\n▶ Test: {description}")
        print(f"  URL: {url}")
        
        try:
            result = extract_instagram_post(url)
            
            media_count = result.get("media_count", 0)
            source = result.get("source", "unknown")
            caption = result.get("caption", "")[:50] + ("..." if len(result.get("caption", "")) > 50 else "")
            elapsed_ms = result.get("elapsed_ms", 0)
            cache_hit = result.get("cache_hit", False)
            error_class = result.get("error_class", "unknown")
            attempts = result.get("attempts", [])
            
            # Summary of attempts
            attempt_summary = []
            for att in attempts:
                method = att.get("method") or att.get("cookie_browser", "unknown")
                ok = att.get("ok")
                media = att.get("media_count", 0)
                status = "✓" if ok else "✗"
                attempt_summary.append(f"{method}({status}, media={media})")
            
            print(f"  ✅ Success")
            print(f"     Media count: {media_count}")
            print(f"     Primary source: {source}")
            print(f"     Caption preview: {caption}")
            print(f"     Time: {elapsed_ms:.0f}ms")
            print(f"     Cache hit: {cache_hit}")
            print(f"     Error class: {error_class}")
            print(f"     Attempts: {' → '.join(attempt_summary)}")
            
            results.append({
                "url": url,
                "ok": True,
                "media_count": media_count,
                "source": source,
                "elapsed_ms": elapsed_ms,
                "jsonld_triggered": any(a.get("method") == "jsonld" for a in attempts),
            })
        
        except Exception as exc:
            print(f"  ❌ Failed: {str(exc)[:200]}")
            results.append({
                "url": url,
                "ok": False,
                "error": str(exc)[:200],
            })
        
        time.sleep(0.5)  # Rate limit
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    
    ok_count = sum(1 for r in results if r.get("ok"))
    jsonld_count = sum(1 for r in results if r.get("jsonld_triggered"))
    total_media = sum(r.get("media_count", 0) for r in results if r.get("ok"))
    avg_time = sum(r.get("elapsed_ms", 0) for r in results if r.get("ok")) / max(ok_count, 1)
    
    print(f"✅ Success rate: {ok_count}/{len(TEST_CASES)} ({100*ok_count//len(TEST_CASES)}%)")
    print(f"📊 Total media extracted: {total_media}")
    print(f"⏱️  Average extraction time: {avg_time:.0f}ms")
    print(f"🔗 JSON-LD fallback triggered: {jsonld_count}/{ok_count} cases")
    
    # Save report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_count": len(TEST_CASES),
        "success_count": ok_count,
        "success_rate": f"{100*ok_count//len(TEST_CASES)}%",
        "total_media_extracted": total_media,
        "avg_extraction_time_ms": f"{avg_time:.0f}",
        "jsonld_fallback_triggered": jsonld_count,
        "results": results,
    }
    
    report_file = REPO_DIR / "memory" / "ig-jsonld-smoke-test.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 Report saved to: {report_file}")
    print("=" * 80)
    
    return 0 if ok_count > 0 else 1

if __name__ == "__main__":
    sys.exit(main())

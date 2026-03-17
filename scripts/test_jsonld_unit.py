#!/usr/bin/env python3
"""
Unit test for JSON-LD fallback layer - tests the extraction logic without hitting IG API.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

def test_jsonld_parsing():
    """Test JSON-LD parsing logic independently"""
    from common.instagram_extract import _run_jsonld
    
    # Mock HTML page with JSON-LD schema
    mock_html = '''
    <html>
    <head>
        <meta property="og:image" content="https://scontent.com/image1.jpg">
        <meta property="og:video" content="https://scontent.com/video1.mp4">
        <meta property="og:description" content="Great post caption here">
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "ImageObject",
            "url": "https://scontent.com/og_image.jpg"
        }
        </script>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": "John Doe"
        }
        </script>
    </head>
    <body>Test content</body>
    </html>
    '''
    
    # Mock requests.get
    with patch('common.instagram_extract.requests') as mock_requests:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_requests.get.return_value = mock_response
        
        result = _run_jsonld("https://www.instagram.com/p/test/")
        
        payload = result.get("payload", {})
        
        # Verify results
        tests = [
            ("payload exists", payload is not None),
            ("source is jsonld", payload.get("source") == "jsonld"),
            ("media_count > 0", payload.get("media_count", 0) > 0),
            ("caption extracted", "Great post caption" in payload.get("caption", "")),
            ("author captured", "John Doe" in payload.get("author", "")),
            ("og:image found", any("image1.jpg" in m.get("url", "") for m in payload.get("media", []))),
        ]
        
        print("=" * 80)
        print("JSON-LD Parsing Unit Tests")
        print("=" * 80)
        
        passed = 0
        for test_name, result_val in tests:
            status = "✅ PASS" if result_val else "❌ FAIL"
            print(f"{status}: {test_name}")
            if result_val:
                passed += 1
        
        print("=" * 80)
        print(f"Results: {passed}/{len(tests)} passed")
        print("=" * 80)
        
        # Print detailed payload
        print("\nExtracted payload:")
        print(json.dumps({
            "source": payload.get("source"),
            "media_count": payload.get("media_count"),
            "caption": payload.get("caption"),
            "author": payload.get("author"),
            "media_urls": [m.get("url") for m in payload.get("media", [])],
        }, indent=2, ensure_ascii=False))
        
        return passed == len(tests)

def test_fallback_chain_logic():
    """Test that JSON-LD is called at the right point in the fallback chain"""
    from common.instagram_extract import extract_instagram_post
    
    # Mock all external calls
    with patch('common.instagram_extract._run_ytdlp') as mock_ytdlp, \
         patch('common.instagram_extract._run_jsonld') as mock_jsonld, \
         patch('common.instagram_extract._run_instaloader') as mock_instaloader:
        
        # yt-dlp returns 0 media but has caption (triggers JSON-LD)
        mock_ytdlp.return_value = {
            "payload": {
                "source": "yt-dlp",
                "media_count": 0,
                "caption": "Test caption",
                "url": "https://www.instagram.com/p/test/",
                "shortcode": "test",
                "author": "",
                "timestamp": None,
                "media": [],
            },
            "meta": {}
        }
        
        # JSON-LD returns some media
        mock_jsonld.return_value = {
            "payload": {
                "source": "jsonld",
                "media_count": 2,
                "caption": "Test caption",
                "url": "https://www.instagram.com/p/test/",
                "shortcode": "test",
                "author": "",
                "timestamp": None,
                "media": [
                    {"type": "image", "url": "https://example.com/1.jpg"},
                    {"type": "image", "url": "https://example.com/2.jpg"},
                ],
            },
            "meta": {}
        }
        
        # Mock cache
        with patch('common.instagram_extract._cache_get', return_value=None), \
             patch('common.instagram_extract._cache_get_stale', return_value=None), \
             patch('common.instagram_extract._cache_put'):
            
            result = extract_instagram_post("https://www.instagram.com/p/test/")
            
            print("\n" + "=" * 80)
            print("Fallback Chain Logic Tests")
            print("=" * 80)
            
            tests = [
                ("JSON-LD called", mock_jsonld.called),
                ("Result source is jsonld", result.get("source") == "jsonld"),
                ("Media count > 0", result.get("media_count", 0) > 0),
                ("Attempts logged", len(result.get("attempts", [])) >= 2),
            ]
            
            passed = 0
            for test_name, result_val in tests:
                status = "✅ PASS" if result_val else "❌ FAIL"
                print(f"{status}: {test_name}")
                if result_val:
                    passed += 1
            
            print("=" * 80)
            print(f"Results: {passed}/{len(tests)} passed")
            print("=" * 80)
            
            print("\nAttempt chain:")
            for i, att in enumerate(result.get("attempts", []), 1):
                print(f"  {i}. {att.get('method') or att.get('cookie_browser', '?')}: "
                      f"ok={att.get('ok')}, media={att.get('media_count', 0)}")
            
            return passed == len(tests)

if __name__ == "__main__":
    print("\n")
    result1 = test_jsonld_parsing()
    result2 = test_fallback_chain_logic()
    
    print("\n" + "=" * 80)
    print("Overall Result")
    print("=" * 80)
    if result1 and result2:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)

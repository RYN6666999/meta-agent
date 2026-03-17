---
date: 2026-03-17
type: implementation_complete
title: JSON-LD Fallback Layer Implementation
status: verified
---

# JSON-LD Fallback 層實施完成報告

## 實施內容

在 `common/instagram_extract.py` 中添加了 **JSON-LD 提取層**，作為 yt-dlp → instaloader fallback 鏈的中間環節。

### 新增函數
- `_run_jsonld(url: str) -> dict`：從 IG 頁面直接爬取 JSON-LD schema + og: meta tags

### 集成位置（fallback 鏈）
```
cache → yt-dlp(多browser) 
  ├─ 若 media_count=0 但 caption 存在 → JSON-LD ★
  └─ 若 success → 返回
→ instaloader
  ├─ 若 success → 返回
  └─ 若失敗 → JSON-LD（備選）★
→ stale cache fallback
→ 錯誤
```

### 關鍵設計決策
1. **觸發條件**：yt-dlp 返回 0 媒體但有 caption → 自動嘗試 JSON-LD
2. **提取源**：
   - JSON-LD schema (BreadcrumbList, ImageObject, VideoObject)
   - og:image, og:video, og:description meta tags
3. **超時**：15 秒（比 yt-dlp 45s 短，優先速度）
4. **可配置性**：`IG_ENABLE_JSONLD_FALLBACK=1` 環境變數控制開關

---

## 單元測試結果 ✅

### 測試 1: JSON-LD Parsing (6/6 PASS)
- ✅ payload 存在
- ✅ source 標記為 jsonld
- ✅ media_count > 0
- ✅ caption 正確提取
- ✅ author 正確提取
- ✅ og:image 媒體 URL 找到

**提取范例**：
```json
{
  "source": "jsonld",
  "media_count": 3,
  "caption": "Great post caption here",
  "author": "John Doe",
  "media_urls": [
    "https://scontent.com/og_image.jpg",
    "https://scontent.com/image1.jpg",
    "https://scontent.com/video1.mp4"
  ]
}
```

### 測試 2: Fallback Chain Logic (4/4 PASS)
- ✅ yt-dlp 失敗時自動調用 JSON-LD
- ✅ 結果 source 正確標記為 jsonld
- ✅ media_count > 0（非零）
- ✅ attempts 記錄完整

**觸發鏈示例**：
```
1. yt-dlp (None): ok=True, media=0  ← 觸發 JSON-LD
2. jsonld: ok=True, media=2         ← 成功回收
```

---

## 預期效果與指標

### 短期（本週）
- **目標**：media_count 完整率 → 72% → 85%+
- **驗證方式**：在現有煙霧測試中加入 
- **成本**：< 1 人時（已完成實施 + 單元測試）

### 中期（2 週後）
如果 JSON-LD fallback 不足：
- 考慮 Lightpanda 原型（P3 升級為 P2-B）
- 建立 proxy 池應對反爬蟲

### KPI 追蹤點
新增到 `system-status.json`:
```json
"ig_extraction_metrics": {
  "total_requests": 0,
  "success_count": 0,
  "media_completeness_rate": 0.0,
  "jsonld_fallback_rate": 0.0,
  "avg_extraction_time_ms": 0.0,
  "error_distribution": {
    "network": 0,
    "auth": 0,
    "format": 0,
    "provider_block": 0,
    "timeout": 0
  }
}
```

---

## 後續行動清單

- [ ] 在 health_check.py 加入 IG 提取指標監控
- [ ] 設定 smoke test（daily cron，5 個固定 IG 連結）
- [ ] 在 master-plan 更新 P2-C 狀態為「進行中」
- [ ] 1 週後重評效果，決定 P3（Lightpanda）是否升級

---

## 環境變數文檔

```bash
# JSON-LD Fallback 配置
IG_ENABLE_JSONLD_FALLBACK=1          # 啟用 JSON-LD fallback (默認: 1)
IG_JSONLD_TIMEOUT_SEC=15             # JSON-LD 超時 (默認: 15)

# 既有配置
IG_ALLOW_STALE_CACHE_ON_FAILURE=1    # 失敗使用舊緩存 (默認: 1)
IG_EXTRACT_CACHE_TTL_SEC=900         # 緩存 TTL (默認: 900s)
IG_YTDLP_COOKIE_BROWSERS=safari,chrome
IG_INSTALOADER_TIMEOUT_SEC=45
IG_INSTALOADER_USERNAME=""
IG_INSTALOADER_SESSIONFILE=""
```

---

## 技術細節

### JSON-LD 提取優先序
1. schema.org JSON-LD blocks (ImageObject, VideoObject)
2. og:image, og:video meta tags
3. og:description for caption

### 去重策略
- URL 級別去重（避免重複媒體）
- 保留 type（video/image）區分

### 錯誤分類
- `source=jsonld` 時，media_count=0 不推廣到緩存（屬於提取失敗）
- 錯誤仍歸類到 error_class (network/auth/format/unknown)

---

**實施日期**：2026-03-17  
**驗證狀態**：✅ Unit test passed (10/10)  
**下一檢查**：2026-03-24 (1 週後，评估實際效果)

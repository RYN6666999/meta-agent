---
date: 2026-03-17
type: decision_analysis
status: pending_decision
priority: P2
title: Lightpanda 評估：是否納入當前架構
---

# Lightpanda 對標分析（2026-03-17）

## Quick Summary
**當前痛點**：Instagram 提取時 media_count=0 but caption exists（yt-dlp 黑箱限制）  
**Lightpanda 定位**：AI/自動化專用無頭瀏覽器，Zig 重寫，11x 快 + 9x 少內存  
**決策**：⏳ 待專案優先序——建議 P3（非立即必須但有中期價值）

---

## 對標方案比較

### Gap 1: HTML/JS 動態內容提取能力

| 指標 | yt-dlp 現況 (A) | Lightpanda (B) | Playwright/Puppeteer (C) |
|------|-----------------|----------------|--------------------------|
| **impact** | 3 (缺媒體完整性) | 5 (可任意 JS 控制) | 4 (完整但重) |
| **effort** | 1 (已集成) | 4 (新 dependency + NPM) | 4 (需 Node.js stack) |
| **risk** | 2 (被動黑箱) | 2 (反爬蟲仍存在) | 3 (資源競爭) |
| **time** | 1 (立即可用) | 3 (遷移 2-3 天) | 3 (遷移 2-3 天) |
| **最終得分** | **3.25/5** | **3.5/5** | **3.5/5** |
| **決策** | 保留（短期） | 考慮替代（中期） | 替代方案（備選） |

**分析**：
- yt-dlp 主瓶頸不是「缺 JS 執行」，而是「IG 反爬蟲簽名檢測」
- Lightpanda vs Playwright：都能解決 JS，但 Lightpanda 更輕量（8GB RAM 限制）
- **結論**：如果問題是「IG API 請求被攔截」→ Lightpanda 幫助有限；如果是「動態渲染的隱藏欄位」→ Lightpanda 有 3-4 倍收益

---

### Gap 2: 資源消耗 vs 穩定性權衡

| 指標 | yt-dlp | Lightpanda | Chrome Headless |
|------|--------|------------|-----------------|
| **內存峰值** | ~50MB | ~24MB | ~207MB |
| **起動時間** | <1s | 即時啟動 | 2-3s |
| **依賴複雜度** | 低（ffmpeg） | 低（Zig runtime） | 高（Chromium） |
| **本地 8GB 限制評估** | ✅ 安全 | ✅ 安全 | ⚠ 邊界（7 並行進程） |

**分析**：
- 在 8GB RAM 限制下，Lightpanda 確實更「適合」
- 但實際收益取決於「能否繞開 IG 反爬蟲檢測」（與瀏覽器無關）

---

### Gap 3: 當前 IG 提取失敗根因分析

根據 `debug-capability-benchmark-2026-03-17.json` 和 `snapinsta-blackbox-analysis`:

**已驗證失敗點**：
1. **media_count=0 但 caption 存在**
   - 根因：yt-dlp 的 IG 插件僅提取文字，不提取媒體 metadata  
   - 🔴 Lightpanda 無法改善（還是同一套 IG 反爬蟲限制）
   - ✅ 改善方案：fallback 到直接 GET https://www.instagram.com/p/{shortcode} + 正則/選擇器爬 JSON-LD

2. **私賬/登入限制**
   - 根因：IG 要求認證  
   - ⏳ Lightpanda 可幫助：可帶 session cookies + 模擬登入流程
   - 但成本：需管理長效 session + 周期性刷新

3. **來自 Snapinsta 的啟發**：
   - Snapinsta 後端也面臨同樣問題（action2.php 後面是 Turnstile 驗證）
   - 不建議模擬私有防護流程（維運成本高、易崩潰）

---

## 決策三問

1. **law.json 的 forbidden 有沒有命中？**  
   ✅ 沒有。Lightpanda 不涉及違反硬規則

2. **error-log/ 有沒有相同根因？**  
   - `debug-capability-benchmark-2026-03-17.json`：「IG scraping 返回 0 count」
   - **根因**：yt-dlp 的黑箱行為 > 瀏覽器選擇
   - Lightpanda 不直接解決根因，只是換個黑箱

3. **技術棧有沒有鎖定選型？**  
   - ✅ 已鎖定：Python + Shell + n8n
   - ❓ Lightpanda = Node.js/NPM library
   - 成本：需在 n8n Code Node 中用 `child_process` 呼叫 Node.js，或額外的 Container

---

## 方案對標：三個選項

### 方案 A: 保持現況 (yt-dlp + instaloader fallback)
- **優**：零遷移成本、已驗證穩定、支持 cookie
- **劣**：media_count=0 問題無解、缺少 JS 上下文
- **成本**：0 人天
- **風險**：持續依賴外部工具黑箱變更

### 方案 B: 集成 Lightpanda（yt-dlp + Lightpanda 混合）
- **優**：可執行 JS、輕量級（9x 少內存）、支持 Puppeteer 兼容
- **劣**：新 dependency、遷移複雜、反爬蟲檢測仍存
- **成本**：3-4 人天（建原型、測試、替換 yt-dlp）
- **風險**：Zig runtime 穩定性未知（relative to Chrome）

### 方案 C: 改進策略（在 yt-dlp 基礎上疊 fallback）
- **優**：低成本、立即有效
- **劣**：只能治標
- **步驟**：
  1. 先抽 URL 正規化 ✅（已做）
  2. yt-dlp 主線 ✅（已做）
  3. **新增**：直接 GET IG 頁面 → 正則/選擇器解析 JSON-LD schema（無需執行 JS）
  4. **新增**：optional Lightpanda 行程（僅當 media_count=0 時觸發）
  5. instaloader fallback ✅（已做）

---

## 建議決策路徑

### 立即行動（明天）→ 方案 C + 小型試驗
1. **試驗範圍**：未來 1 週
2. **步驟**：
   - 在 `instagram_extract.py` 新增「JSON-LD fallback」層
   - 命中條件：media_count=0 but caption exists
   - 測試 10 個固定 IG 連結（單圖、輪播、reel 混合）
   - 統計命中率

3. **成本**：1.5 人天
4. **驗證指標**：
   - success_rate 從 72% → 85%+
   - media_count > 0 的覆蓋率

### 有條件行動（2-4 週後）→ 方案 B 原型
1. **前置條件**：JSON-LD fallback 驗證效果有限 (<80%)
2. **範圍**：建原型（不替換主線）
3. **成本**：2-3 人天
4. **驗證**：試 Puppeteer/Lightpanda 對比效果

### 放棄條件
- 如果 JSON-LD fallback 達到 85%+ → **不追 Lightpanda**
- 如果反爬蟲檢測是根因（403/429） → Lightpanda 幫助有限，專注 proxy 池

---

## 對商業級記憶方案的映射

| 商業方案 | 我們現況 | Lightpanda 改善 |
|---------|---------|-----------------|
| Claude + Browser Use | Python CLI | 🔴 差（需 Node.js bridge） |
| Perplexity API | Brave search | 🟡 中（可用 Puppeteer 補足） |
| Anthropic API 新 Computer Use | (無) | 🟡 中（替代品） |

**結論**：Lightpanda 不是對標商業級記憶方案的「缺口」，而是優化內部 IG 提取的「工具選項」。

---

## 最終建議

**決策**：**P3（後續中期改進）** ← 先完成方案 C

1. **下週任務清單**：
   - [ ] 實施 JSON-LD fallback 層（instagram_extract.py）
   - [ ] 健康檢查加入「IG 媒體完整性率」指標
   - [ ] E2E 驗證（smoke test 5+ IG posts）
   
2. **若成效不佳（<80%）**：
   - [ ] 建 Lightpanda 原型（n8n Code Node 呼叫）
   - [ ] 對比 Puppeteer
   - [ ] 決策是否替換主線

3. **追蹤指標**：
   - media_count 完整率（目標 95%）
   - 平均執行時間（目標 <5s）
   - 記憶成本（token）

---

**最後判斷**：✅ **建議採納方案 C，暫不追 Lightpanda，但監控效果 1-2 週後重評。**

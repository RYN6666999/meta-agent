# Snapinsta 黑箱分析與可移植策略（2026-03-17）

## 結論摘要
- Snapinsta 的核心不是公開 API，而是前端表單 + 後端私有端點組合。
- 前端主流程為：使用者貼上網址 -> 通過 Cloudflare Turnstile -> 帶 token 與 session POST 到 action2.php。
- 直接程式化呼叫 action2.php（缺少有效 Turnstile）會得到 HTTP 200 但空 body，無法作為穩定 API 使用。
- 可借鑑的是「流程設計與韌性策略」，不建議借鑑其私有端點呼叫方式。

## 已驗證觀察
1. HTML 存在防機器人驗證與 token 欄位
- cf-turnstile: data-sitekey 與 success/error callback
- hidden fields: action=post, lang=en, token=<動態值>
- script: /public/js/main.min.js?v=1.88

2. main.min.js 核心行為
- submit 時建立 FormData(form)
- XMLHttpRequest POST 到 action2.php
- 成功時將 response 包成 script 並注入執行（insertAndExecute）
- 先檢查輸入是否含 URL，再送出

3. 端點可達性測試
- 對 action2.php 直接 POST（含 url/action/lang/token，無有效 cf-turnstile-response）
- 回應：HTTP 200
- body: 0 bytes
- 推論：後端受 Turnstile/session 條件保護，非公開可重用 API

## 技術映射：可移植 vs 不建議

### 可移植（建議）
1. 輸入容錯層
- 從任意貼上文字中先抽取第一個 URL，再做網域與 path 正規化。
- 目的：降低使用者貼入雜訊造成失敗率。

2. 多層擷取策略
- 既有 yt-dlp 主線 + cookies + instaloader fallback 保留。
- 增加「前置輸入清洗」與「錯誤分類」，提升可觀測性與可回歸性。

3. 可觀測回傳欄位
- 保留並強化 cache_hit、elapsed_ms、attempts。
- 後續可加 error_class（network/auth/format/provider_block）統計。

4. 反爬策略遵循
- 使用官方可接受資料來源與公開工具（yt-dlp/instaloader）
- 避免模擬破解第三方私有防護流程。

### 不建議（不採用）
1. 直接依賴 action2.php 私有端點
- 受驗證與站方變更影響大，長期不穩。

2. 複製其 script 注入執行模式
- 安全風險高，不適合 MCP/後端服務。

## 對 meta-agent 的落地建議
1. 已落地
- 將 Snapinsta 的「先抽 URL 再處理」概念導入 common/instagram_extract.py。

2. 下一步
- 在 system-status 增加 IG 成功率與 error_class 日統計。
- 設定 smoke 測試組合：單圖、輪播、reel、受限內容，固定每日檢查。

## 風險與邊界
- 私帳、登入限制、地區限制仍可能導致外部工具失敗。
- 需持續依據錯誤統計調整 fallback 順序與 timeout。
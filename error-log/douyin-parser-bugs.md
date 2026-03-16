---
date: 2026-03-12
type: error_fix
status: active
last_triggered: 2026-03-16
base_score: 120.0
expires_after_days: 365
source: Douyin Parser workflow 除錯
---

# Douyin Parser — Bug 根因文檔

**Workflow ID:** JLDy5AGM7aM2rTlhy3K4i
**紀錄日期:** 2026-03-12
**狀態:** BUG 7 未解

---

## BUG 1：Webhook 404「not registered」✅ 已解

**症狀:** `POST http://localhost:5678/webhook/douyin → 404`

**根因:** n8n v2 將 active 與 published 分開。MCP API 更新的 workflow 只變成 draft，不會自動 publish。Production webhook 只在 published 版本生效。

**URL 對照:**
| 狀態 | URL |
|---|---|
| Published | `http://localhost:5678/webhook/douyin` |
| Draft | `http://localhost:5678/webhook/{workflowId}/webhook/douyin` |

**修正:** `douyin_sender.py` 的 N8N_URL 改為 draft URL 格式，或確保 workflow 已 publish。

---

## BUG 2：Code Node 無法使用 child_process ✅ 已解

**症狀:** `Error: child_process is not allowed`（即使 docker-compose.yml 已設定環境變數）

**根因:** n8n v2.11.2 引入 `@n8n/task-runner`，Code node 在獨立 subprocess 執行，不繼承 docker-compose 環境變數。

**辨識方式:** stack trace 中出現 `@n8n/task-runner/dist/js-task-runner/js-task-runner.js`

**修正:** `docker-compose.yml` 加入：
```yaml
- N8N_RUNNERS_ENABLED=false
```
重啟: `docker compose down && docker compose up -d`

---

## BUG 3：updateNode 語法錯誤 ✅ 已解

**根因:** 要改的欄位必須放在 `updates` 子物件內。

```json
// 錯誤
{"type": "updateNode", "nodeId": "xxx", "parameters": {...}}

// 正確
{"type": "updateNode", "nodeId": "xxx", "updates": {"parameters": {...}}}
```

---

## BUG 4：addConnection 失敗 ✅ 已解

**修正:** 改用 `n8n_update_full_workflow`，注意 `name` 為必填：
```json
{"id": "JLDy5AGM7aM2rTlhy3K4i", "name": "Douyin Parser", "nodes": [...], "connections": {...}}
```

---

## BUG 5：updateNode 找不到節點 ✅ 已解

**根因:** `updateNode` 需用 `nodeId`（UUID），不能用 name（顯示名稱）。

**查詢節點 ID:** `n8n_get_workflow → data.nodes[].id`

---

## BUG 6：yt-dlp 需要 cookies ✅ 已解

**症狀:** `Fresh cookies (not necessarily logged in) are needed`

**修正:**
```bash
docker cp /tmp/douyin_cookies.txt n8n:/home/node/.n8n/douyin_cookies.txt
docker exec n8n chmod 644 /home/node/.n8n/douyin_cookies.txt
```

yt-dlp 指令加 `--cookies /home/node/.n8n/douyin_cookies.txt`

---

## BUG 7：msToken 缺失 — API 回傳空 body ⚠️ 未解

**症狀:** 即使有 sessionid（2026-04-20 到期），仍回傳空 body

**根因:** Douyin API 需要 `msToken`，此 cookie 由頁面 JavaScript 動態生成，一般匯出工具無法捕捉。

**yt-dlp 原始碼確認:**
`/usr/local/lib/python3.11/dist-packages/yt_dlp/extractor/tiktok.py` 第 1469 行有 TODO

**驗證:**
```bash
docker exec n8n grep -i "mstoken" /home/node/.n8n/douyin_cookies.txt
# 若無輸出 → msToken 缺失
```

**正確的 cookies 匯出流程:**
1. 瀏覽器開啟 `https://www.douyin.com/`
2. **等待 5-10 秒**讓 JavaScript 執行（msToken 才會寫入）
3. 立即用「Get cookies.txt LOCALLY」Chrome 擴充匯出

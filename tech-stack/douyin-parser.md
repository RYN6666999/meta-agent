---
date: 2026-03-14
type: tech_decision
status: active
last_triggered: 2026-03-16
expires_after_days: 180
source: Douyin Parser workflow 建立
---

# Douyin Parser — 技術棧與路徑總覽

## 關鍵路徑

| 項目 | 路徑 |
|---|---|
| docker-compose | `/Users/ryan/Projects/n8n/docker-compose.yml` |
| n8n 資料庫 | 容器內 `/home/node/.n8n/database.sqlite` |
| Douyin cookies | 容器內 `/home/node/.n8n/douyin_cookies.txt` |
| 音訊暫存 | 容器內 `/tmp/dyin_audio.mp3` |
| Obsidian 輸出 | `/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/TikTok_Notes/` |
| Obsidian 索引 | `/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/douyin-cache.md` |
| 發送腳本 | `/Users/ryan/Desktop/douyin_sender.py` |
| n8n API key | `~/Library/Application Support/Claude/claude_desktop_config.json` → `N8N_API_KEY` |

## Workflows

### Douyin Parser（快速通道）
- **ID:** `JLDy5AGM7aM2rTlhy3K4i`
- **Active:** true
- **最後更新:** 2026-03-14

| 節點名稱 | Node ID | 類型 |
|---|---|---|
| Webhook | `fd73693c-c93e-4147-8bbd-e17f27e6ed4e` | webhook |
| Get Douyin URL | `get-douyin-url-001` | httpRequest |
| Download Audio | `download-audio-001` | code |
| Process Audio | `process-audio-001` | code |
| Write Basic Note | `write-basic-note-001` | code |
| Respond to Webhook | `respond-001` | respondToWebhook |
| Trigger Enrich | `trigger-enrich-001` | httpRequest |

### Douyin Enricher（非同步深度處理）
- **ID:** `gcXBDEFa5joixhX6`
- **Active:** true
- **建立日期:** 2026-03-14

| 節點名稱 | Node ID | 類型 |
|---|---|---|
| Webhook | `enrich-webhook-001` | webhook |
| Respond 200 | `enrich-respond-001` | respondToWebhook |
| Build Combined Prompt | `enrich-prompt-001` | code |
| Extract All | `enrich-extract-001` | httpRequest |
| Update Note | `enrich-write-001` | code |

## API Keys（存放於 .env，勿明文寫入程式碼）

| 服務 | 變數名 |
|---|---|
| Groq | `$GROQ_API_KEY` |
| Dify API Key | `$DIFY_APP_KEY` |
| Dify Dataset ID | `$DIFY_DATASET_ID` (`efdc8d39-2812-456f-8ce8-496fe7cefe51`) |

## docker-compose.yml 關鍵環境變數

```yaml
- N8N_HOST=localhost
- N8N_PORT=5678
- N8N_PROTOCOL=http
- WEBHOOK_URL=http://localhost:5678/
- GENERIC_TIMEZONE=Asia/Taipei
- TZ=Asia/Taipei
- N8N_RESTRICT_FILE_ACCESS_TO=/home/node/.n8n;/home/node/obsidian
- NODE_FUNCTION_ALLOW_BUILTIN=child_process,fs,path,os
- NODE_FUNCTION_ALLOW_EXTERNAL=*
- N8N_RUNNERS_ENABLED=false   # 關鍵：停用 task runner，否則 child_process 無法使用
```

## 轉錄服務

- **Groq Whisper API**（雲端，免費額度高）
- 備用：本地 Whisper（需更多 RAM，8GB Mac 不建議）

## 資料流（雙管道架構）

```
douyin_sender.py
    → POST /webhook/douyin（Douyin Parser）
        → Get Douyin URL
        → Download Audio
        → Process Audio（Groq Whisper 轉錄）
        → Write Basic Note（寫入 Obsidian 基礎筆記）
        → Respond to Webhook（立即回應，不卡使用者）
        → Trigger Enrich → POST /webhook/enrich（Douyin Enricher）
                              → Respond 200（立即回應）
                              → Build Combined Prompt
                              → Extract All（LLM 深度萃取）
                              → Update Note（更新 Obsidian 筆記）
```

**設計意圖：**
- Parser 負責快速完成（下載、轉錄、寫入基礎筆記），讓使用者盡快收到回應
- Enricher 非同步執行深度分析，完成後更新同一份筆記
- 兩個 workflow 都已 active（Published 狀態）

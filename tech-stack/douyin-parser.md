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

## Workflow

- **ID:** `JLDy5AGM7aM2rTlhy3K4i`
- **名稱:** Douyin Parser

## 節點 ID 對照

| 節點名稱 | Node ID |
|---|---|
| Webhook | `fd73693c-c93e-4147-8bbd-e17f27e6ed4e` |
| yt-dlp Extract | `ytdlp-code-v2` |
| Transcribe Audio | `b2c3d4e5-f6a7-8901-bcde-222222222222` |
| Extract Knowledge | `c3d4e5f6-a7b8-9012-cdef-333333333333` |
| Write Notes | `d4e5f6a7-b8c9-0123-defa-444444444444` |
| Dify Ingest | `dify-ingest-001` |
| Respond to Webhook | `8bbc0fd5-ee44-47bc-afd5-f3191839be84` |

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

## 資料流

```
douyin_sender.py
    → POST webhook
    → yt-dlp Extract（需 cookies + msToken）
    → Transcribe Audio（Groq Whisper）
    → Extract Knowledge
    → Write Notes（寫入 Obsidian）
    → Dify Ingest（寫入 Dify 知識庫）
    → Respond to Webhook
```

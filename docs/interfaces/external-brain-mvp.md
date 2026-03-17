# 外掛大腦 MVP 介面規格

## 目標
讓任何外部工具可以透過標準 HTTP 直接使用 meta-agent 的記憶能力，而不必依賴 MCP 客戶端。

## Endpoints
- `POST /api/v1/query`
  輸入：`q`, `mode`
  輸出：搜尋結果與時間戳

- `POST /api/v1/telegram/webhook/{secret}`
  輸入：Telegram Update payload
  輸出：是否成功回覆 Telegram

- `GET /api/v1/telegram/config`
  輸入：無
  輸出：Telegram 功能是否啟用、必要環境變數是否已設定

- `POST /api/v1/ingest`
  輸入：`content`, `mem_type`, `title`
  輸出：ingest 結果與成功訊息

- `GET /api/v1/rules`
  輸入：`category`
  輸出：law.json 指定分類

- `POST /api/v1/log-error`
  輸入：`root_cause`, `solution`, `topic`, `context`
  輸出：error-log 寫入結果

- `GET /api/v1/health`
  輸出：API、自身、最近 health check、最近 E2E 狀態

- `GET /api/v1/trace`
  輸入：`topic`
  輸出：truth-source / error-log / pending-decisions 中與主題相關的來源片段

## 認證
- Header：`Authorization: Bearer <META_AGENT_API_KEY>`
- 開發期可用 `.env` 中 `META_AGENT_API_KEY` 控制

## Telegram 遠端機制（參考 golem/nanoclaw 協議）
1. 在 `.env` 新增：
  - `TELEGRAM_BOT_TOKEN=<your_bot_token>`
  - `TELEGRAM_WEBHOOK_SECRET=<long_random_secret>`
  - `CLOUDFLARE_TUNNEL_TOKEN=<named_tunnel_token>`（商業建議）
  - `MOBILE_PUBLIC_BASE_URL=https://<your-fixed-domain>`（商業建議）
2. 服務啟動後，設定 Telegram webhook：
  - `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<PUBLIC_URL>/api/v1/telegram/webhook/<TELEGRAM_WEBHOOK_SECRET>&secret_token=<TELEGRAM_WEBHOOK_SECRET>`
3. 在 TG 對 bot 發送訊息，可用指令：
  - `/q <問題>`：查記憶
  - `/ingest <內容>`：寫入 verified memory（自動加 `[CONFIRMED]`）
  - `/protocol <GOLEM 協議內容>`：執行 `[GOLEM_MEMORY]/[GOLEM_ACTION]/[GOLEM_REPLY]` 區塊
  - `/sync`：觸發電腦同步作業（obsidian ingest）
  - `/sync full`：同步 + 健康檢查
  - `/status`：查看 health/e2e/auto-recovery 最新狀態

## 開機自動可用（手機可立即下指令）
1. 載入 launchd 服務（只需一次）：
  - `chmod +x /Users/ryan/meta-agent/scripts/start_mobile_bridge.sh`
  - `chmod +x /Users/ryan/meta-agent/scripts/mobile_bridge_watchdog.sh`
  - `cp /Users/ryan/meta-agent/scripts/com.meta-agent.mobile-bridge.plist ~/Library/LaunchAgents/`
  - `cp /Users/ryan/meta-agent/scripts/com.meta-agent.mobile-watchdog.plist ~/Library/LaunchAgents/`
  - `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.meta-agent.mobile-bridge.plist >/dev/null 2>&1 || true`
  - `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.meta-agent.mobile-watchdog.plist >/dev/null 2>&1 || true`
  - `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.meta-agent.mobile-bridge.plist`
  - `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.meta-agent.mobile-watchdog.plist`
  - `launchctl enable gui/$(id -u)/com.meta-agent.mobile-bridge`
  - `launchctl enable gui/$(id -u)/com.meta-agent.mobile-watchdog`
  - `launchctl kickstart -k gui/$(id -u)/com.meta-agent.mobile-bridge`
  - `launchctl kickstart -k gui/$(id -u)/com.meta-agent.mobile-watchdog`
2. 每次開機會自動完成：
  - 啟動 API (`uvicorn`)
  - 啟動 cloudflared Named Tunnel（固定網域）
  - 重新綁定 Telegram webhook 到目前 tunnel URL
3. 自我修復（每 60 秒 watchdog）：
  - API 不通 → 自動重啟 API
  - tunnel 掛掉 → 自動重啟 cloudflared
  - webhook 漂移（URL 變更）→ 自動重綁 Telegram webhook
  - webhook 持續失敗 → 自動切換 Telegram long polling 備援通道
  - 發現事故 → 自動寫入 error-log + 嘗試 ingest 進可調用真理源
4. 除錯檔案：
  - `/tmp/meta-agent-api.log`
  - `/tmp/meta-agent-cloudflared.log`
  - `/tmp/meta-agent-telegram-setwebhook.json`
  - `/tmp/com.meta-agent.mobile-watchdog.out.log`
  - `/tmp/com.meta-agent.mobile-watchdog.err.log`

## 驗證
- 啟動：`python -m uvicorn api.server:app --host 127.0.0.1 --port 9901`
- Smoke test：`python scripts/test_api.py --base-url http://127.0.0.1:9901`
- Telegram 設定檢查：`curl -H "Authorization: Bearer <META_AGENT_API_KEY>" http://127.0.0.1:9901/api/v1/telegram/config`

## 升級建議（商業版）
1. 使用 Named Tunnel（固定網域 + token），避免 Quick Tunnel 1033 與 URL 漂移。
2. 將 `MOBILE_PUBLIC_BASE_URL` 指向固定網域，讓 webhook URL 穩定不變。
3. 保留 watchdog，作為 API/tunnel/webhook 三層自癒保護。
4. 若 Telegram webhook 因 Telegram 端限制失敗，系統會自動 fallback 到 `scripts/telegram_poll_bridge.py`。

## Named Tunnel 切換驗收（5+1 檢查）
執行：`python3 /Users/ryan/meta-agent/scripts/mobile_bridge_acceptance.py`

檢查項目：
1. launchd 服務：mobile-bridge / mobile-watchdog 已載入
2. 本機 API：`/api/v1/telegram/config` 可用
3. tunnel 模式：named（有 token + 固定網域）
4. 公網可達：public URL 可以連到 API
5. Telegram webhook：綁定 URL 與目前 public URL 一致
6. watchdog 狀態：`memory/status/mobile_bridge_watchdog.json` 更新時間新鮮

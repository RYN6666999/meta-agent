# Mobile Bridge Monitoring Runbook

## 目的
快速確認 Telegram -> webhook -> API 處理鏈路是否真的有事件進站，避免監聽錯誤 log sink。

## 標準步驟
1. 執行 `python3 scripts/mobile_bridge_acceptance.py`。
2. 確認 `runtime_log_sink` 為 `PASS`，並記下 `sink=<path>`。
3. 監聽該 sink：`tail -n 20 -F <path>`。
4. 在 Telegram 發送訊息後，確認以下三段：
   - `incoming update_id/chat_id/text`
   - `process start`
   - `process done ... delivered=True`

## 診斷分支
- `runtime_log_sink=FAIL bridge process missing`:
  - 重啟 launchd job：
    - `launchctl kickstart -k gui/$(id -u)/com.meta-agent.mobile-bridge`
    - `launchctl kickstart -k gui/$(id -u)/com.meta-agent.mobile-watchdog`
- `telegram_webhook=FAIL current=...`:
  - 重新綁定 webhook 或檢查 PUBLIC URL。
- webhook 200 但無 incoming：
  - 代表可能在看錯 log 檔或 hit 到另一個進程，回到步驟 1 重跑 acceptance。

## 注意事項
- `pending_update_count=0` 不代表「沒送訊息」，只代表沒有排隊中的未投遞更新。
- 必須以 API runtime log 的 incoming/process 訊息判定是否收到實際對話事件。

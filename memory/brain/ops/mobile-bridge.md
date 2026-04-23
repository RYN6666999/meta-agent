# mobile-bridge 操作手冊

> 錯誤歷史 → bugs/mobile-bridge.md。這裡只放操作指令。

## 快速指令

```bash
# 重啟（標準）
launchctl kickstart -k gui/$(id -u)/com.meta-agent.mobile-bridge

# 查 log（正確路徑）
tail -n 50 -F /private/tmp/meta-agent-api.log

# ⚠️ 錯誤路徑（永遠 0 bytes，不要看這個）
# /tmp/com.meta-agent.mobile-bridge.out.log

# 查實際 log 路徑（動態確認）
lsof -p $(pgrep -f 'uvicorn.*9901') -a -d 1,2

# 診斷：先查誰死了
pgrep -f cloudflared && echo "cloudflared OK" || echo "cloudflared DEAD"
pgrep -f "uvicorn.*9901" && echo "uvicorn OK" || echo "uvicorn DEAD"

# 驗收
python3 /Users/ryan/meta-agent/scripts/mobile_bridge_acceptance.py
```

## 服務資訊
| 項目 | 值 |
|------|-----|
| Port | 9901 |
| Plist | `com.meta-agent.mobile-bridge` |
| Telegram Webhook | `https://bot.3141919ryanfeofjpewfp.uk/api/v1/telegram/webhook/papa-bridge-20260317` |

## 環境變數（.env）
| 變數 | 預設值 | 說明 |
|------|--------|------|
| TELEGRAM_QUERY_STRATEGY | smart_fallback | 或 strict_persona |
| TELEGRAM_PROGRESS_STYLE | throttled | 或 raw |

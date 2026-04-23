# mobile-bridge 已知問題

> 蒸餾自 69 個 error-log（2026-03-17 ~ 2026-04-23）。每次新事件只更新「已知事實」區塊，並在時間線 append 一行。

---

## ✅ 目前最佳已知事實（最後更新：2026-04-23）

### 根本問題（未解決）
**cloudflared tunnel 持續崩潰，但 watchdog 修的是 uvicorn（錯誤目標）。**
這是 36 天無法根治的原因：每次都重啟了錯的服務。

### 已確認的三個根因

| # | 根因 | 頻率 | 修法 |
|---|------|------|------|
| RC-1 | `cloudflared tunnel process not running` | 每日多次 | 重啟 cloudflared（不是 uvicorn）|
| RC-2 | `mobile API endpoint not healthy (health_code=000)` | 每日多次 | RC-1 的症狀，cloudflared 死了 API 就不可達 |
| RC-3 | `cloudflared did not emit quick tunnel url` | 偶發 | 等待或重新啟動 cloudflared |
| RC-4 | `telegram setWebhook failed` | RC-1 引發 | cloudflared 重啟後 URL 改變，需重新 bind |

### 關鍵診斷：為何重啟 uvicorn 沒用
```
cloudflared 死掉 → 外部無法連到 port 9901 → health_code=000
watchdog 誤判為 uvicorn 問題 → 重啟 uvicorn
uvicorn 根本沒死，重啟無效 → 5 分鐘後再度 health_code=000
→ 無限循環
```

### 正確修法
```bash
# 1. 確認誰真的死了
pgrep -f cloudflared   # 如果沒輸出 → cloudflared 死了
pgrep -f uvicorn       # 如果沒輸出 → uvicorn 死了（少見）

# 2. 重啟 mobile bridge（含 cloudflared）
launchctl kickstart -k gui/$(id -u)/com.meta-agent.mobile-bridge

# 3. 驗收
python3 /Users/ryan/meta-agent/scripts/mobile_bridge_acceptance.py
```

### 關鍵路徑
| 項目 | 值 |
|------|-----|
| API port | 9901 |
| 正確日誌路徑 | `/private/tmp/meta-agent-api.log` |
| **錯誤路徑（永遠 0 bytes）** | `/tmp/com.meta-agent.mobile-bridge.out.log` |
| Telegram webhook | `https://bot.3141919ryanfeofjpewfp.uk/api/v1/telegram/webhook/papa-bridge-20260317` |
| 日誌監控 | `tail -n 20 -F /private/tmp/meta-agent-api.log` |
| 查 log 路徑 | `lsof -p $(pgrep -f 'uvicorn.*9901') -a -d 1,2` |

### 待查（尚未有答案）
- [ ] cloudflared 為什麼會死？是 macOS 的 launchd timeout？網路問題？還是記憶體？
- [ ] 換成 named tunnel（不用 quick tunnel）是否能解決 URL 每次改變的問題？
- [ ] watchdog 的修復邏輯是否需要改為先查 cloudflared，再查 uvicorn？

---

## 📅 事件時間線（只 append）

- 2026-03-17: 首次記錄。多種根因同日出現：tunnel-down、webhook-bind-failed、url-missing
- 2026-03-18: api-down + tunnel-down + webhook-bind-failed 持續
- 2026-03-19 ~ 2026-03-20: 每日 api-down + tunnel-down
- 2026-03-21: 確認 root_cause = "cloudflared tunnel process not running"（首次明確記錄）
- 2026-03-22 ~ 2026-04-16: 每日 api-down + tunnel-down，同樣根因，無根本修復
- 2026-04-17: CRM ES Module refactor 同日發生，tunnel 仍持續崩潰
- 2026-04-19 ~ 2026-04-23: 持續崩潰，今日（2026-04-23）已記錄 12 次崩潰
- **累計：69 個 error-log 文件，0 個根本修復**

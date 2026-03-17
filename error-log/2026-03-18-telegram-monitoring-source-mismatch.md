---
date: 2026-03-18
type: error_fix
status: active
last_triggered: 2026-03-18
expires_after_days: 365
topic: telegram-monitoring-source-mismatch
---

# Error: 監聽了錯誤的 log sink，導致誤判「收不到 TG 訊息」

## 根本原因
- 監聽 `/tmp/com.meta-agent.mobile-bridge.out.log` 與 `/tmp/com.meta-agent.mobile-bridge.err.log`。
- 但實際 uvicorn stdout/stderr FD 指向 `/private/tmp/meta-agent-api.log`。
- 因此 tail 一直空白，造成「以為沒有 webhook 進站」的錯誤判讀。

## 正確資訊
- 以 `lsof -p <uvicorn_pid> -a -d 1,2` 判定當下真實 log sink。
- 本次實測 sink 為 `/private/tmp/meta-agent-api.log`。
- 該檔可看到 Telegram 事件：
  - `[telegram] incoming update_id=... chat_id=... text='...'`
  - `[telegram] process start ...`
  - `[telegram] process done ... delivered=True`

## 證據摘要
- `getWebhookInfo`：url 正確，`pending_update_count=0`。
- 本機 webhook probe：`POST /api/v1/telegram/webhook/...` 回 `{"ok":true,"accepted":true,...}`。
- API log 中可見多筆來自 Telegram IP 的 `POST /api/v1/telegram/webhook/... 200 OK` 與 incoming/process log。

## 修正措施
- `scripts/mobile_bridge_acceptance.py` 新增 `runtime_log_sink` 檢查，直接輸出 `pid` 與真實 sink 檔案。
- 排障時優先使用 acceptance 結果，不再預設固定 tail 某兩個檔案。

## 防再犯檢查清單
- 先跑 `python3 scripts/mobile_bridge_acceptance.py`。
- 若 `runtime_log_sink=PASS`，tail 該 sink 檔案再看 webhook。
- 若 webhook 有 200 但無 incoming 行，先檢查是否 hit 到不同進程/不同 log 檔。

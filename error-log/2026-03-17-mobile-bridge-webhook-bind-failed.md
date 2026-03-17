---
date: 2026-03-17
type: error_fix
status: active
last_triggered: 2026-03-17
expires_after_days: 365
topic: mobile-bridge-webhook-bind-failed
---

# Error: telegram setWebhook failed

## 根本原因
telegram setWebhook failed

## 解決方案
retry bind in next watchdog cycle

## 背景
target=Binary file /tmp/meta-agent-cloudflared.log matches/api/v1/telegram/webhook/papa-bridge-20260317 response={"ok":false,"error_code":400,"description":"Bad Request: invalid webhook URL specified"}

## 2026-03-17 18:08:10
- root_cause: telegram setWebhook failed
- solution: retry bind in next watchdog cycle
- context: target=2026-03-17T10:00:00Z INF |  https://indicates-emotional-cruises-expenditures.trycloudflare.com                        |/api/v1/telegram/webhook/papa-bridge-20260317 response={"ok":false,"error_code":400,"description":"Bad Request: invalid webhook URL specified"}

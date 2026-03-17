---
date: 2026-03-18
type: error_fix
status: active
last_triggered: 2026-03-18
expires_after_days: 365
topic: mobile-bridge-webhook-bind-failed
---

# Error: telegram setWebhook failed

## 根本原因
telegram setWebhook failed

## 解決方案
retry bind in next watchdog cycle

## 背景
target=https://contract-conducting-atmospheric-kurt.trycloudflare.com/api/v1/telegram/webhook/papa-bridge-20260317 response={"ok":false,"error_code":400,"description":"Bad Request: bad webhook: Failed to resolve host: Name or service not known"}

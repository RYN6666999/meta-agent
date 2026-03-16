---
date: 2026-03-16
type: error_fix
status: active
last_triggered: 2026-03-16
expires_after_days: 365
topic: claude-bug-log-discipline
---

# Error: Claude 發現並修正 bug 後，沒有立即呼叫 log_error，需要用戶提醒才補記。本身違反「發現即記錄」原則。

## 根本原因
Claude 發現並修正 bug 後，沒有立即呼叫 log_error，需要用戶提醒才補記。本身違反「發現即記錄」原則。

## 解決方案
每次修正任何 bug 後，立刻在同一輪呼叫 log_error，不等用戶提醒，不批次到最後才補。

## 背景
當次 session 修正了 groq-proxy DNS、webhook URL、PreToolUse hook 等 bug，但沒有即時 log，等用戶指出才補。

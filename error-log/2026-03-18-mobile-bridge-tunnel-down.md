---
date: 2026-03-18
type: error_fix
status: active
last_triggered: 2026-03-18
expires_after_days: 365
topic: mobile-bridge-tunnel-down
---

# Error: cloudflared tunnel process not running

## 根本原因
cloudflared tunnel process not running

## 解決方案
restart cloudflared via watchdog

## 背景
pattern=cloudflared tunnel run --token mode=named

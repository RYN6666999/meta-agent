---
date: 2026-04-23
type: verified_truth
status: active
last_triggered: 2026-04-23
expires_after_days: 365
source: bug-closeout autopipeline
---

# mobile-bridge-root-cause

## Summary
uvicorn 36天無法啟動，每日產生69個假陽性error-log

## Root Cause
memory-mcp目錄從根目錄移至tools/後，api/server.py等4個腳本仍指向舊路徑，導致uvicorn每次import就FileNotFoundError崩潰；cloudflared全程正常

## Fix
ln -sf /Users/ryan/meta-agent/tools/memory-mcp /Users/ryan/meta-agent/memory-mcp（建立symlink）

## Verification
mobile_bridge_acceptance.py 7/7 passed；uvicorn PID確認存活

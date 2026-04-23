# mobile-bridge-root-cause

- timestamp: 2026-04-23 12:55:27
- summary: uvicorn 36天無法啟動，每日產生69個假陽性error-log
- root_cause: memory-mcp目錄從根目錄移至tools/後，api/server.py等4個腳本仍指向舊路徑，導致uvicorn每次import就FileNotFoundError崩潰；cloudflared全程正常
- fix: ln -sf /Users/ryan/meta-agent/tools/memory-mcp /Users/ryan/meta-agent/memory-mcp（建立symlink）
- verify: mobile_bridge_acceptance.py 7/7 passed；uvicorn PID確認存活

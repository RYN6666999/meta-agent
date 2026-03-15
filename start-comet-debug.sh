#!/bin/bash
# 啟動 Comet + 遠端除錯（讓 claude-devtools MCP 可接入）
/Applications/Comet.app/Contents/MacOS/Comet \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/comet-debug-profile \
  "$@" &

echo "✅ Comet 已啟動，遠端除錯 port: 9222"
echo "   MCP 連線: http://127.0.0.1:9222"

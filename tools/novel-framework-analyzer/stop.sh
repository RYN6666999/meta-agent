#!/usr/bin/env bash
# 局心欲變 Novel Analyzer — 停止腳本

PORT=8766
PID_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.server.pid"

PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo $PIDS | xargs kill
  rm -f "$PID_FILE"
  echo "🛑 已停止 port $PORT (PID $PIDS)"
else
  rm -f "$PID_FILE"
  echo "ℹ️  沒有在跑的伺服器"
fi

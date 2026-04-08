#!/usr/bin/env bash
# 局心欲變 Novel Analyzer — 啟動腳本
# 用法：./start.sh
# 功能：啟動 FastAPI server，自動開瀏覽器

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
PID_FILE="$DIR/.server.pid"
LOG_FILE="$DIR/.server.log"
PORT=8766

# ── 檢查是否已在跑 ────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "⚡ 伺服器已在跑 (PID $OLD_PID)，直接開瀏覽器..."
    open "http://localhost:$PORT"
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

# ── 啟動伺服器 ────────────────────────────────────────────
echo "🚀 啟動 Novel Analyzer..."
cd "$DIR"
# 先殺掉殘留的 port process
lsof -ti :$PORT | xargs kill 2>/dev/null || true

"$VENV/bin/uvicorn" server:app --host 0.0.0.0 --port $PORT > "$LOG_FILE" 2>&1 &
LAUNCHER_PID=$!
echo "$LAUNCHER_PID" > "$PID_FILE"

echo "📄 Log: $LOG_FILE"
echo "🌐 URL:  http://localhost:$PORT"
echo "✅ PID:  $(cat $PID_FILE)"

# 等 server 就緒再開瀏覽器
for i in $(seq 1 20); do
  if curl -sf "http://localhost:$PORT/" > /dev/null 2>&1; then
    open "http://localhost:$PORT"
    break
  fi
  sleep 0.5
done

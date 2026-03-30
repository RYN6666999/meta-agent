#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/Users/ryan/meta-agent"
OUT_FILE="$BASE_DIR/memory/toolbox-health.json"
NOW="$(date '+%Y-%m-%d %H:%M:%S')"

check_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    echo true
  else
    echo false
  fi
}

check_port() {
  local port="$1"
  if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo true
  else
    echo false
  fi
}

toolbox_console_file="$(check_file "$BASE_DIR/scripts/toolbox-console/package.json")"
decision_file="$(check_file "$BASE_DIR/scripts/decision-engine.py")"
truth_file="$(check_file "$BASE_DIR/scripts/truth-xval.py")"
novel_file="$(check_file "$BASE_DIR/tools/novel-framework-analyzer/server.py")"
memory_file="$(check_file "$BASE_DIR/tools/memory-mcp/server.py")"
douyin_sender_file="$(check_file "/Users/ryan/Desktop/douyin_sender.py")"
douyin_refresh_file="$(check_file "/Users/ryan/Projects/n8n/scripts/refresh_douyin_cookie.py")"

port_5188="$(check_port 5188)"
port_5678="$(check_port 5678)"
port_8000="$(check_port 8000)"
port_8765="$(check_port 8765)"

cat > "$OUT_FILE" <<JSON
{
  "checked_at": "$NOW",
  "files": {
    "toolbox_console_package_json": $toolbox_console_file,
    "decision_engine": $decision_file,
    "truth_xval": $truth_file,
    "novel_server": $novel_file,
    "memory_mcp_server": $memory_file,
    "douyin_sender": $douyin_sender_file,
    "douyin_cookie_refresh": $douyin_refresh_file
  },
  "ports": {
    "toolbox_ui_5188": $port_5188,
    "n8n_5678": $port_5678,
    "douyin_api_8000": $port_8000,
    "novel_ui_8765": $port_8765
  }
}
JSON

echo "Wrote $OUT_FILE"
cat "$OUT_FILE"

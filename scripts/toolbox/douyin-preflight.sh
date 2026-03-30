#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/Users/ryan/meta-agent"
OUT_FILE="$BASE_DIR/memory/douyin-preflight.json"
NOW="$(date '+%Y-%m-%d %H:%M:%S')"

check_port() {
  local port="$1"
  if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo true
  else
    echo false
  fi
}

check_py_module() {
  local mod="$1"
  if python3 - <<PY >/dev/null 2>&1
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("$mod") else 1)
PY
  then
    echo true
  else
    echo false
  fi
}

sender_exists=false
refresh_exists=false
[[ -f "/Users/ryan/Desktop/douyin_sender.py" ]] && sender_exists=true
[[ -f "/Users/ryan/Projects/n8n/scripts/refresh_douyin_cookie.py" ]] && refresh_exists=true

n8n_up="$(check_port 5678)"
api_up="$(check_port 8000)"
mod_cookie="$(check_py_module browser_cookie3)"
mod_tk="$(check_py_module tkinter)"

ready=false
if [[ "$sender_exists" == true && "$refresh_exists" == true && "$n8n_up" == true && "$api_up" == true && "$mod_cookie" == true && "$mod_tk" == true ]]; then
  ready=true
fi

cat > "$OUT_FILE" <<JSON
{
  "checked_at": "$NOW",
  "tool": "douyin",
  "ready": $ready,
  "files": {
    "sender": $sender_exists,
    "cookie_refresh": $refresh_exists
  },
  "ports": {
    "n8n_5678": $n8n_up,
    "douyin_api_8000": $api_up
  },
  "python_modules": {
    "browser_cookie3": $mod_cookie,
    "tkinter": $mod_tk
  }
}
JSON

echo "Wrote $OUT_FILE"
cat "$OUT_FILE"

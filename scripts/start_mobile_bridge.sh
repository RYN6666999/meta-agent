#!/bin/zsh
set -euo pipefail

ROOT="/Users/ryan/meta-agent"
ENV_FILE="$ROOT/.env"
API_LOG="/tmp/meta-agent-api.log"
TUNNEL_LOG="/tmp/meta-agent-cloudflared.log"
PUBLIC_URL_FILE="/tmp/meta-agent-public-url.txt"
TUNNEL_MODE_FILE="/tmp/meta-agent-tunnel-mode.txt"
POLL_LOG="/tmp/meta-agent-telegram-poll.log"

cd "$ROOT"

if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    export "$key=$value"
  done < "$ENV_FILE"
fi

PYTHON_BIN="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

CLOUDFLARED_BIN="/opt/homebrew/bin/cloudflared"
if [[ ! -x "$CLOUDFLARED_BIN" ]]; then
  CLOUDFLARED_BIN="$(command -v cloudflared || true)"
fi
if [[ -z "$CLOUDFLARED_BIN" ]]; then
  echo "[mobile-bridge] cloudflared not found" >> "$TUNNEL_LOG"
  exit 1
fi

TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"
PUBLIC_BASE_URL="${MOBILE_PUBLIC_BASE_URL:-}"

resolve_quick_url() {
  local tries=0
  local max_tries=30
  local found=""
  while [[ $tries -lt $max_tries ]]; do
    tries=$((tries + 1))
    found=$(sed -n 's#.*\(https://[a-zA-Z0-9.-]*\.trycloudflare\.com\).*#\1#p' "$TUNNEL_LOG" | head -n 1)
    if [[ -n "$found" ]]; then
      echo "$found"
      return 0
    fi
    sleep 1
  done
  return 1
}

ensure_poll_bridge_running() {
  if ! pgrep -f "telegram_poll_bridge.py" >/dev/null 2>&1; then
    nohup "$PYTHON_BIN" "$ROOT/scripts/telegram_poll_bridge.py" > "$POLL_LOG" 2>&1 &
  fi
}

stop_poll_bridge() {
  pkill -f "telegram_poll_bridge.py" >/dev/null 2>&1 || true
}

set_webhook_with_retry() {
  local webhook_url="$1"
  local attempt=0
  local max_attempts=12
  local resp=""
  while [[ $attempt -lt $max_attempts ]]; do
    attempt=$((attempt + 1))
    resp=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
      --data-urlencode "url=$webhook_url" \
      --data-urlencode "secret_token=$TELEGRAM_WEBHOOK_SECRET" \
      --data "drop_pending_updates=true")
    echo "$resp" > /tmp/meta-agent-telegram-setwebhook.json

    if echo "$resp" | grep -q '"ok":true'; then
      return 0
    fi

    retry_after=$(echo "$resp" | sed -n 's/.*"retry_after":\([0-9][0-9]*\).*/\1/p' | head -n 1)
    if echo "$resp" | grep -q 'Failed to resolve host'; then
      sleep 5
    elif [[ -n "${retry_after:-}" ]]; then
      sleep $((retry_after + 1))
    else
      sleep $((attempt * 2))
    fi
  done
  return 1
}

# Restart API to ensure fresh env is loaded after reboot
pkill -f "uvicorn api.server:app --host 127.0.0.1 --port 9901" >/dev/null 2>&1 || true
nohup "$PYTHON_BIN" -m uvicorn api.server:app --host 127.0.0.1 --port 9901 > "$API_LOG" 2>&1 &

# Restart tunnel (named preferred, quick fallback)
pkill -f "cloudflared tunnel" >/dev/null 2>&1 || true
if [[ -n "$TUNNEL_TOKEN" && -n "$PUBLIC_BASE_URL" ]]; then
  nohup "$CLOUDFLARED_BIN" tunnel run --token "$TUNNEL_TOKEN" > "$TUNNEL_LOG" 2>&1 &
  echo "named" > "$TUNNEL_MODE_FILE"
else
  nohup "$CLOUDFLARED_BIN" tunnel --url http://127.0.0.1:9901 --no-autoupdate > "$TUNNEL_LOG" 2>&1 &
  echo "quick" > "$TUNNEL_MODE_FILE"
fi

MODE="$(cat "$TUNNEL_MODE_FILE" 2>/dev/null || echo quick)"
URL=""

if [[ "$MODE" == "named" ]]; then
  URL="$PUBLIC_BASE_URL"
else
  URL="$(resolve_quick_url || true)"
fi
echo "$URL" > "$PUBLIC_URL_FILE"

if [[ -z "${URL:-}" ]]; then
  echo "[mobile-bridge] tunnel URL not found" >> "$TUNNEL_LOG"
  exit 1
fi

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_WEBHOOK_SECRET:-}" ]]; then
  echo "[mobile-bridge] TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET missing" >> "$TUNNEL_LOG"
  exit 1
fi

WEBHOOK_URL="$URL/api/v1/telegram/webhook/$TELEGRAM_WEBHOOK_SECRET"

if set_webhook_with_retry "$WEBHOOK_URL"; then
  stop_poll_bridge
else
  echo "[mobile-bridge] setWebhook failed after retries, fallback to poll" >> "$TUNNEL_LOG"
  ensure_poll_bridge_running
fi

echo "[mobile-bridge] ready: $WEBHOOK_URL" >> "$TUNNEL_LOG"

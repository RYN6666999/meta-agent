#!/bin/zsh
set -euo pipefail

ROOT="/Users/ryan/meta-agent"
ENV_FILE="$ROOT/.env"
API_LOG="/tmp/meta-agent-api.log"
TUNNEL_LOG="/tmp/meta-agent-cloudflared.log"
PUBLIC_URL_FILE="/tmp/meta-agent-public-url.txt"
STATE_FILE="/tmp/meta-agent-mobile-bridge-state.txt"
INCIDENT_SCRIPT="$ROOT/scripts/mobile_bridge_incident.py"
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

API_KEY="${META_AGENT_API_KEY:-${API_KEY:-${N8N_API_KEY:-}}}"
TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"
PUBLIC_BASE_URL="${MOBILE_PUBLIC_BASE_URL:-}"

current_tunnel_mode() {
  if [[ -n "$TUNNEL_TOKEN" && -n "$PUBLIC_BASE_URL" ]]; then
    echo "named"
  else
    echo "quick"
  fi
}

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

record_incident() {
  local topic="$1"
  local cause="$2"
  local solution="$3"
  local context="$4"
  if [[ -x "$PYTHON_BIN" && -f "$INCIDENT_SCRIPT" ]]; then
    "$PYTHON_BIN" "$INCIDENT_SCRIPT" \
      --topic "$topic" \
      --root-cause "$cause" \
      --solution "$solution" \
      --context "$context" >/dev/null 2>&1 || true
  fi
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

start_api() {
  pkill -f "uvicorn api.server:app --host 127.0.0.1 --port 9901" >/dev/null 2>&1 || true
  nohup "$PYTHON_BIN" -m uvicorn api.server:app --host 127.0.0.1 --port 9901 > "$API_LOG" 2>&1 &
}

start_tunnel() {
  if [[ -z "$CLOUDFLARED_BIN" ]]; then
    return 1
  fi
  pkill -f "cloudflared tunnel" >/dev/null 2>&1 || true
  if [[ "$(current_tunnel_mode)" == "named" ]]; then
    nohup "$CLOUDFLARED_BIN" tunnel run --token "$TUNNEL_TOKEN" > "$TUNNEL_LOG" 2>&1 &
    echo "named" > "$TUNNEL_MODE_FILE"
  else
    nohup "$CLOUDFLARED_BIN" tunnel --url http://127.0.0.1:9901 --no-autoupdate > "$TUNNEL_LOG" 2>&1 &
    echo "quick" > "$TUNNEL_MODE_FILE"
  fi
}

ensure_api() {
  local code
  code=$(curl -s -o /tmp/meta-agent-api-health.json -w "%{http_code}" \
    -H "Authorization: Bearer $API_KEY" \
    "http://127.0.0.1:9901/api/v1/telegram/config" || true)
  if [[ "$code" != "200" ]]; then
    record_incident "mobile-bridge-api-down" \
      "mobile API endpoint not healthy" \
      "restart uvicorn via watchdog" \
      "health_code=$code"
    start_api
    sleep 2
  fi
}

ensure_tunnel() {
  local pattern
  if [[ "$(current_tunnel_mode)" == "named" ]]; then
    pattern="cloudflared tunnel run --token"
  else
    pattern="cloudflared tunnel --url http://127.0.0.1:9901"
  fi

  if ! pgrep -f "$pattern" >/dev/null 2>&1; then
    record_incident "mobile-bridge-tunnel-down" \
      "cloudflared tunnel process not running" \
      "restart cloudflared via watchdog" \
      "pattern=$pattern mode=$(current_tunnel_mode)"
    start_tunnel
    sleep 2
  fi
}

ensure_webhook() {
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_WEBHOOK_SECRET:-}" ]]; then
    return 0
  fi

  local pub
  if [[ "$(current_tunnel_mode)" == "named" ]]; then
    pub="$PUBLIC_BASE_URL"
  else
    pub="$(resolve_quick_url || true)"
  fi

  if [[ -z "$pub" ]]; then
    record_incident "mobile-bridge-url-missing" \
      "cloudflared has no resolvable public url" \
      "keep watchdog retries and restart tunnel" \
      "mode=$(current_tunnel_mode) log=/tmp/meta-agent-cloudflared.log"
    return 0
  fi
  echo "$pub" > "$PUBLIC_URL_FILE"

  local target
  target="$pub/api/v1/telegram/webhook/$TELEGRAM_WEBHOOK_SECRET"

  local current
  current=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
    | sed -n 's/.*"url":"\([^"]*\)".*/\1/p' | head -n 1)

  local last
  last=""
  if [[ -f "$STATE_FILE" ]]; then
    last=$(cat "$STATE_FILE")
  fi

  if [[ "$current" != "$target" || "$last" != "$target" ]]; then
    if set_webhook_with_retry "$target"; then
      echo "$target" > "$STATE_FILE"
      stop_poll_bridge
    else
      local resp
      resp=$(cat /tmp/meta-agent-telegram-setwebhook.json 2>/dev/null || echo "setWebhook failed")
      record_incident "mobile-bridge-webhook-bind-failed" \
        "telegram setWebhook failed" \
        "retry bind in next watchdog cycle" \
        "target=$target response=$resp"
      ensure_poll_bridge_running
    fi
  fi
}

ensure_api
ensure_tunnel
ensure_webhook

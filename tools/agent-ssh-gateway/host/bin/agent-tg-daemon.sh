#!/usr/bin/env bash
# agent-tg-daemon.sh — P8.2 Telegram 雙向指令頻道
#
# 部署位置：/usr/local/bin/agent-tg-daemon.sh（目標主機）
# 常駐方式：launchd com.agentbot.tg-daemon
#
# 設計原則：
#   - Telegram getUpdates long-poll（不需 HTTPS webhook）
#   - 只接受 AUTHORIZED_CHAT_ID 的訊息，其餘靜默丟棄
#   - 指令嚴格限定：/status /jobs /requeue /help（不執行任意 shell）
#   - /requeue 只顯示指令，不自動執行（人工確認後才 cp）
#   - 讀取 gateway-policy.sh 以取得目前 GATEWAY_MODE（唯讀，不執行）
#
# 設定來源（優先順序）：
#   1. 環境變數 TG_BOT_TOKEN / TG_AUTHORIZED_CHAT_ID
#   2. SECRETS_FILE（.secrets.json）

set -uo pipefail

# ── 路徑設定 ─────────────────────────────────────────────────────────

# 部署到 /usr/local/bin 後 BASH_SOURCE 路徑無法反推專案目錄
# 優先用 launchd plist 注入的 AGENT_SSH_GATEWAY_DIR，否則用 WorkingDirectory
if [[ -n "${AGENT_SSH_GATEWAY_DIR:-}" ]]; then
  PROJECT_DIR="${AGENT_SSH_GATEWAY_DIR}"
elif [[ -f "${PWD}/.secrets.json" ]]; then
  PROJECT_DIR="${PWD}"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

SECRETS_FILE="${PROJECT_DIR}/.secrets.json"
JOBS_DIR="${PROJECT_DIR}/jobs"
POLICY_FILE="/usr/local/bin/gateway-policy.sh"
AGENT_HOME="/Users/agentbot"
ENABLED_FLAG="${AGENT_HOME}/.ssh/enabled.flag"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/tg-daemon.log"
PID_FILE="${LOG_DIR}/tg-daemon.pid"

# ── 設定載入 ─────────────────────────────────────────────────────────

_load_secret() {
  local key="$1"
  python3 -c "
import json, sys
try:
    d = json.load(open('${SECRETS_FILE}'))
    print(d['telegram']['${key}'])
except Exception as e:
    sys.exit(1)
" 2>/dev/null
}

BOT_TOKEN="${TG_BOT_TOKEN:-}"
AUTHORIZED_CHAT_ID="${TG_AUTHORIZED_CHAT_ID:-}"

if [[ -z "${BOT_TOKEN}" ]] && [[ -f "${SECRETS_FILE}" ]]; then
  BOT_TOKEN="$(_load_secret botToken)"
fi

if [[ -z "${AUTHORIZED_CHAT_ID}" ]] && [[ -f "${SECRETS_FILE}" ]]; then
  AUTHORIZED_CHAT_ID="$(_load_secret chatId)"
fi

if [[ -z "${BOT_TOKEN}" ]]; then
  echo "ERROR: TG_BOT_TOKEN not set and not found in ${SECRETS_FILE}" >&2
  exit 1
fi

if [[ -z "${AUTHORIZED_CHAT_ID}" ]]; then
  echo "ERROR: TG_AUTHORIZED_CHAT_ID not set and not found in ${SECRETS_FILE}" >&2
  exit 1
fi

TG_API="https://api.telegram.org/bot${BOT_TOKEN}"

# ── Log ──────────────────────────────────────────────────────────────

mkdir -p "${LOG_DIR}"

log() {
  local level="$1"; shift
  echo "$(date '+%Y-%m-%dT%H:%M:%S') ${level} $*" >> "${LOG_FILE}"
}

# ── Telegram API ─────────────────────────────────────────────────────

send_message() {
  local chat_id="$1"
  local text="$2"
  local payload
  payload=$(python3 -c "
import json, sys
print(json.dumps({
    'chat_id': int('${chat_id}'),
    'text': sys.argv[1],
    'parse_mode': 'HTML'
}))" "${text}" 2>&1) || {
    log "ERROR send_message python3 failed: ${payload}"
    return 1
  }
  local resp
  resp=$(curl -s --max-time 10 -X POST "${TG_API}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "${payload}" 2>&1)
  local ok
  ok=$(echo "${resp}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('ok','?'))" 2>/dev/null)
  if [[ "${ok}" != "True" ]]; then
    log "WARN send_message failed ok=${ok} resp=${resp}"
  fi
}

# ── Gateway Policy（唯讀）────────────────────────────────────────────

get_gateway_mode() {
  if [[ -f "${POLICY_FILE}" ]]; then
    grep '^GATEWAY_MODE=' "${POLICY_FILE}" | head -1 | sed 's/GATEWAY_MODE=//;s/"//g'
  else
    echo "unknown"
  fi
}

# ── 指令處理 ─────────────────────────────────────────────────────────

cmd_status() {
  local mode
  mode=$(get_gateway_mode)

  local gw_status="UNKNOWN"
  if [[ -f "${ENABLED_FLAG}" ]]; then
    gw_status="ENABLED"
  fi

  local failed_count=0
  local incoming_count=0
  local running_count=0

  if [[ -d "${JOBS_DIR}/failed" ]]; then
    failed_count=$(find "${JOBS_DIR}/failed" -maxdepth 1 -name "*.json" ! -name "*.result.json" 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [[ -d "${JOBS_DIR}/incoming" ]]; then
    incoming_count=$(find "${JOBS_DIR}/incoming" -maxdepth 1 -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [[ -d "${JOBS_DIR}/running" ]]; then
    running_count=$(find "${JOBS_DIR}/running" -maxdepth 1 -name "*.json" ! -name "*.result.json" 2>/dev/null | wc -l | tr -d ' ')
  fi

  printf '<b>SSH Gateway Status</b>\n\nGateway: %s\nMode: <code>%s</code>\n\nJobs:\n  incoming : %s\n  running  : %s\n  failed   : %s\n\n%s' \
    "${gw_status}" "${mode}" \
    "${incoming_count}" "${running_count}" "${failed_count}" \
    "$(date '+%Y-%m-%d %H:%M:%S')"
}

cmd_jobs() {
  local failed_dir="${JOBS_DIR}/failed"

  if [[ ! -d "${failed_dir}" ]]; then
    echo "No failed jobs directory found."
    return
  fi

  local jobs
  mapfile -t jobs < <(find "${failed_dir}" -maxdepth 1 -name "*.json" ! -name "*.result.json" -exec basename {} .json \; 2>/dev/null | sort)

  if [[ ${#jobs[@]} -eq 0 ]]; then
    echo "No failed jobs."
    return
  fi

  local out
  out="<b>Failed Jobs (${#jobs[@]})</b>\n"
  for job_id in "${jobs[@]}"; do
    local ts=""
    local result_file="${failed_dir}/${job_id}.result.json"
    if [[ -f "${result_file}" ]]; then
      ts=$(python3 -c "
import json, sys
try:
    d = json.load(open('${result_file}'))
    v = d.get('failed_at') or d.get('completed_at') or ''
    print(v[:16])
except:
    pass
" 2>/dev/null)
    fi
    out+="• <code>${job_id}</code> ${ts}\n"
  done
  out+="\nUse /requeue &lt;job_id&gt; to re-queue"
  printf '%b' "${out}"
}

cmd_requeue() {
  local job_id="$1"

  if [[ -z "${job_id}" ]]; then
    echo "Usage: /requeue &lt;job_id&gt;"
    return
  fi

  # 防注入：job_id 只允許英數字、dash、underscore
  if ! [[ "${job_id}" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Invalid job_id format. Only alphanumeric, dash, underscore allowed."
    return
  fi

  local failed_file="${JOBS_DIR}/failed/${job_id}.json"

  if [[ ! -f "${failed_file}" ]]; then
    echo "Job not found in failed/: <code>${job_id}</code>"
    return
  fi

  printf '<b>Re-queue command for %s</b>\n\n<code>cp "%s/failed/%s.json" \\\n   "%s/incoming/%s.json"</code>\n\nRun this on the host. Job will be picked up on next runner poll.' \
    "${job_id}" \
    "${JOBS_DIR}" "${job_id}" \
    "${JOBS_DIR}" "${job_id}"
}

cmd_help() {
  cat <<'EOF'
<b>SSH Gateway Bot</b>

/status — Gateway mode &amp; job counts
/jobs — List failed jobs
/requeue &lt;job_id&gt; — Show re-queue command
/help — This message
EOF
}

# ── 訊息解析 ─────────────────────────────────────────────────────────

parse_updates() {
  local tmp_file="$1"
  # 輸出格式：update_id\tchat_id\ttext（每行一條 update）
  python3 - "${tmp_file}" <<'PYEOF'
import json, sys

try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)

for update in data.get("result", []):
    uid = update.get("update_id", 0)
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id", "")
    text = msg.get("text", "").strip().replace("\t", " ").replace("\n", " ")
    if chat_id:
        print(f"{uid}\t{chat_id}\t{text}")
PYEOF
}

dispatch() {
  local chat_id="$1"
  local text="$2"

  # 提取指令與第一個參數
  local cmd arg1=""
  cmd=$(echo "${text}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
  arg1=$(echo "${text}" | awk '{print $2}')

  log "INFO cmd=${cmd} arg1=${arg1} chat_id=${chat_id}"

  local reply
  case "${cmd}" in
    /status)  reply=$(cmd_status) ;;
    /jobs)    reply=$(cmd_jobs) ;;
    /requeue) reply=$(cmd_requeue "${arg1}") ;;
    /help)    reply=$(cmd_help) ;;
    /start)   reply=$(cmd_help) ;;
    *)
      reply="Unknown command: <code>${cmd}</code>\n\nUse /help to see available commands."
      ;;
  esac

  send_message "${chat_id}" "${reply}"
}

# ── Main Loop ────────────────────────────────────────────────────────

cleanup() {
  log "INFO daemon stopping"
  [[ -f "${PID_FILE}" ]] && rm -f "${PID_FILE}"
}
trap cleanup EXIT TERM INT

echo $$ > "${PID_FILE}"
log "INFO daemon started pid=$$ authorized_chat_id=${AUTHORIZED_CHAT_ID}"
log "INFO jobs_dir=${JOBS_DIR}"

LAST_UPDATE_ID=0
TMP_FILE=$(mktemp)
trap 'rm -f "${TMP_FILE}"; cleanup' EXIT TERM INT

while true; do
  # Long-poll: timeout=30 讓 Telegram 伺服器等最多 30 秒再回應
  OFFSET=$(( LAST_UPDATE_ID + 1 ))
  HTTP_CODE=$(curl -s --max-time 35 -o "${TMP_FILE}" -w "%{http_code}" \
    "${TG_API}/getUpdates?offset=${OFFSET}&timeout=30&allowed_updates=%5B%22message%22%5D" \
    2>/dev/null || echo "000")

  if [[ "${HTTP_CODE}" != "200" ]]; then
    log "WARN getUpdates http_code=${HTTP_CODE}, retrying in 5s"
    sleep 5
    continue
  fi

  # 解析並處理每條 update
  while IFS=$'\t' read -r uid chat_id text; do
    [[ -z "${uid}" ]] && continue

    # 更新 offset（確保下次跳過此 update）
    if (( uid > LAST_UPDATE_ID )); then
      LAST_UPDATE_ID=${uid}
    fi

    # 安全過濾：只處理授權 chat_id
    if [[ "${chat_id}" != "${AUTHORIZED_CHAT_ID}" ]]; then
      log "WARN unauthorized chat_id=${chat_id} text=${text}"
      continue
    fi

    # 只處理 / 開頭的指令
    if [[ "${text}" != /* ]]; then
      continue
    fi

    dispatch "${chat_id}" "${text}"

  done < <(parse_updates "${TMP_FILE}")

done

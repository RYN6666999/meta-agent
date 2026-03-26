#!/usr/bin/env bash
# agent-gateway.sh — AI Agent SSH 命令 Gateway
#
# 部署位置：/usr/local/bin/agent-gateway.sh（目標主機）
# 用途：作為 SSH ForceCommand，限制 AI agent 只能執行受控命令
#
# Exit codes：
#   0 = 命令執行成功
#   1 = 命令被拒絕 / 開關關閉 / 命令為空
#   N = 被執行命令的原始 exit code

set -uo pipefail

# ── 設定 ─────────────────────────────────────────────────────────────

AGENT_HOME="/Users/agentbot"
ENABLED_FLAG="${AGENT_HOME}/.ssh/enabled.flag"
WORKSPACE="${AGENT_HOME}/workspace"
LOG_DIR="${AGENT_HOME}/logs"
LOG_FILE="${LOG_DIR}/agent-ssh.log"

# ── Log 初始化 ────────────────────────────────────────────────────────

mkdir -p "${LOG_DIR}"

log() {
  local level="$1"
  shift
  local ts
  ts=$(date '+%Y-%m-%dT%H:%M:%S')
  printf '%s | %-5s | %s\n' "${ts}" "${level}" "$*" >> "${LOG_FILE}"
}

deny() {
  local reason="$1"
  log "DENY " "cmd=${REQUESTED_CMD:-<empty>} reason=${reason}"
  echo "[gateway] 拒絕: ${reason}" >&2
  exit 1
}

# ── 讀取命令 ──────────────────────────────────────────────────────────

REQUESTED_CMD="${SSH_ORIGINAL_COMMAND:-}"

if [[ -z "${REQUESTED_CMD}" ]]; then
  deny "empty command (interactive shell not allowed)"
fi

# ── 開關檢查 ──────────────────────────────────────────────────────────

if [[ ! -f "${ENABLED_FLAG}" ]]; then
  deny "agent-switch is OFF"
fi

# ── 黑名單 ───────────────────────────────────────────────────────────
# 模式為 extended regex，match 命令任意位置（防止管線繞過）

BLACKLIST=(
  '(^|[[:space:]|;`$])sudo([[:space:]]|$)'
  '(^|[[:space:]|;`$])su([[:space:]]|$)'
  'rm[[:space:]]+-[^[:space:]]*r[^[:space:]]*[[:space:]].*/'
  'rm[[:space:]]+-rf[[:space:]]+'
  '(^|[[:space:]])reboot([[:space:]]|$)'
  '(^|[[:space:]])shutdown([[:space:]]|$)'
  '(^|[[:space:]])halt([[:space:]]|$)'
  '(^|[[:space:]])poweroff([[:space:]]|$)'
  '(^|[[:space:]])mkfs[[:space:]]'
  'dd[[:space:]]+if='
  '(^|[[:space:]|;`])nc([[:space:]]|$)'
  '(^|[[:space:]|;`])ncat([[:space:]]|$)'
  '(^|[[:space:]|;`])socat([[:space:]]|$)'
  '(^|[[:space:]|;`])ssh([[:space:]]|$)'
  '(^|[[:space:]|;`])scp([[:space:]]|$)'
  'curl[^|]*\|[[:space:]]*(ba)?sh'
  'wget[^|]*\|[[:space:]]*(ba)?sh'
  '>[[:space:]]*/etc/'
  '>[[:space:]]*/boot/'
)

for pattern in "${BLACKLIST[@]}"; do
  if echo "${REQUESTED_CMD}" | grep -qE "${pattern}"; then
    deny "blacklisted pattern matched: ${pattern}"
  fi
done

# ── 切換工作目錄 ──────────────────────────────────────────────────────

mkdir -p "${WORKSPACE}"
cd "${WORKSPACE}" || deny "cannot cd to workspace"

# ── 執行命令 ──────────────────────────────────────────────────────────

log "ALLOW" "cmd=${REQUESTED_CMD}"

bash -lc "${REQUESTED_CMD}"
EXIT_CODE=$?

log "DONE " "cmd=${REQUESTED_CMD} exit=${EXIT_CODE}"
exit ${EXIT_CODE}

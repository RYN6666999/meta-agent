#!/usr/bin/env bash
# agent-gateway.sh — AI Agent SSH 命令 Gateway（P7 Lite）
#
# 部署位置：/usr/local/bin/agent-gateway.sh（目標主機）
# 用途：作為 SSH ForceCommand，限制 AI agent 只能執行受控命令
#
# P7 Lite：固定 2 層治理（enforce only）
#   Layer 1 — HARD_DENY（永遠擋，patterns 來自 gateway-policy.sh）
#   Layer 2 — ALLOWLIST（只允許白名單，其餘拒絕）
#
# 規則來源：同目錄的 gateway-policy.sh
# 開關：agent-switch on / off
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

# ── Policy 載入 ───────────────────────────────────────────────────────

POLICY_FILE="$(dirname "$0")/gateway-policy.sh"
if [[ -f "${POLICY_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${POLICY_FILE}"
else
  # Fallback：policy 遺失時安全拒絕一切
  HARD_DENY=()
  ALLOWLIST=()
fi

# ── Log 初始化 + Rotation ─────────────────────────────────────────────
#
# Size-based rotation：超過 512KB 時輪轉，最多保留 3 份備份。

LOG_MAX_BYTES=524288  # 512 KB

mkdir -p "${LOG_DIR}"

rotate_log() {
  [[ -f "${LOG_FILE}" ]] || return 0
  local size
  size=$(stat -f%z "${LOG_FILE}" 2>/dev/null || stat -c%s "${LOG_FILE}" 2>/dev/null || echo 0)
  if (( size > LOG_MAX_BYTES )); then
    [[ -f "${LOG_FILE}.2" ]] && mv "${LOG_FILE}.2" "${LOG_FILE}.3"
    [[ -f "${LOG_FILE}.1" ]] && mv "${LOG_FILE}.1" "${LOG_FILE}.2"
    mv "${LOG_FILE}" "${LOG_FILE}.1"
  fi
}

rotate_log

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

# ── Layer 1：硬拒絕（永遠擋）────────────────────────────────────────

for pattern in "${HARD_DENY[@]:-}"; do
  if echo "${REQUESTED_CMD}" | grep -qE "${pattern}"; then
    log "DENY " "cmd=${REQUESTED_CMD} reason=hard-deny pattern=${pattern}"
    echo "[gateway] 拒絕: hard-deny pattern matched" >&2
    exit 1
  fi
done

# ── Layer 2：Allowlist（只允許白名單）───────────────────────────────

CMD_TOKEN=$(echo "${REQUESTED_CMD}" | awk '{print $1}' | xargs basename 2>/dev/null || echo "")

_in_allowlist() {
  local token="$1"
  for entry in "${ALLOWLIST[@]:-}"; do
    [[ "${token}" == "${entry}" ]] && return 0
  done
  return 1
}

if ! _in_allowlist "${CMD_TOKEN}"; then
  log "DENY " "cmd=${REQUESTED_CMD} reason=not-in-allowlist token=${CMD_TOKEN}"
  echo "[gateway] 拒絕: 命令不在白名單（${CMD_TOKEN}）" >&2
  exit 1
fi

# ── 允許通過，切換工作目錄並執行 ───────────────────────────────────

mkdir -p "${WORKSPACE}"
cd "${WORKSPACE}" || deny "cannot cd to workspace"

log "ALLOW" "cmd=${REQUESTED_CMD}"

bash -lc "${REQUESTED_CMD}"
EXIT_CODE=$?

log "DONE " "cmd=${REQUESTED_CMD} exit=${EXIT_CODE}"
exit ${EXIT_CODE}

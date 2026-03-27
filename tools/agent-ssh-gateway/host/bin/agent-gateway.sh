#!/usr/bin/env bash
# agent-gateway.sh — AI Agent SSH 命令 Gateway
#
# 部署位置：/usr/local/bin/agent-gateway.sh（目標主機）
# 用途：作為 SSH ForceCommand，限制 AI agent 只能執行受控命令
#
# P7 升級：四模式分級命令治理（Controlled Allowlist Mode）
#   模式與規則由同目錄的 gateway-policy.sh 控制。
#   切換模式：agent-switch mode <legacy-blacklist|audit|enforce|break-glass>
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

# ── Policy 載入（P7）─────────────────────────────────────────────────
#
# source gateway-policy.sh（與本腳本同目錄）
# 若不存在則退回 legacy-blacklist 模式。

POLICY_FILE="$(dirname "$0")/gateway-policy.sh"
if [[ -f "${POLICY_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${POLICY_FILE}"
else
  GATEWAY_MODE="legacy-blacklist"
  HARD_DENY=()
  ALLOWLIST=()
  OBSERVELIST=()
fi

# ── Log 初始化 + Rotation ─────────────────────────────────────────────
#
# P5.2 size-based rotation：超過 512KB 時輪轉，最多保留 3 份備份。
# stat 語法：macOS 用 -f%z，Linux 用 -c%s。

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

# P7：可分析的結構化決策 log
# 格式：timestamp | LEVEL | mode=... decision=... category=... cmd=... reason=...
log_decision() {
  local decision="$1"   # allow / deny / observe
  local category="$2"   # allowlist / hard-deny / observe / unknown / legacy / break-glass
  local reason="$3"
  local ts level
  ts=$(date '+%Y-%m-%dT%H:%M:%S')
  level=$(echo "${decision}" | tr '[:lower:]' '[:upper:]')
  printf '%s | %-5s | mode=%s decision=%s category=%s cmd=%s reason=%s\n' \
    "${ts}" "${level}" "${GATEWAY_MODE:-unknown}" \
    "${decision}" "${category}" \
    "${REQUESTED_CMD:-<empty>}" "${reason}" >> "${LOG_FILE}"
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

# ── P7 決策流 ─────────────────────────────────────────────────────────

# Step 1：硬拒絕（Layer 1 — 永遠擋，不論 GATEWAY_MODE）
for pattern in "${HARD_DENY[@]:-}"; do
  if echo "${REQUESTED_CMD}" | grep -qE "${pattern}"; then
    log_decision "deny" "hard-deny" "hard-deny pattern matched: ${pattern}"
    echo "[gateway] 拒絕: hard-deny pattern matched" >&2
    exit 1
  fi
done

# 取出命令第一個 token（basename），用於 allowlist / observelist 比對
CMD_TOKEN=$(echo "${REQUESTED_CMD}" | awk '{print $1}' | xargs basename 2>/dev/null || echo "")

# Allowlist 比對 helper
_in_allowlist() {
  local token="$1"
  for entry in "${ALLOWLIST[@]:-}"; do
    [[ "${token}" == "${entry}" ]] && return 0
  done
  return 1
}

# Observelist 比對 helper
_in_observelist() {
  local token="$1"
  for entry in "${OBSERVELIST[@]:-}"; do
    [[ "${token}" == "${entry}" ]] && return 0
  done
  return 1
}

# Step 2：依 GATEWAY_MODE 決定行為
case "${GATEWAY_MODE:-legacy-blacklist}" in

  legacy-blacklist)
    # 到這裡代表未命中 HARD_DENY，沿用舊語義直接放行
    log_decision "allow" "legacy" "legacy-blacklist mode"
    ;;

  audit)
    # 白名單觀察期：未命中允許但強制記錄，不中斷工作流
    if _in_allowlist "${CMD_TOKEN}"; then
      log_decision "allow" "allowlist" "in allowlist"
    elif _in_observelist "${CMD_TOKEN}"; then
      log_decision "allow" "observe" "in observelist, audit mode"
    else
      log_decision "allow" "unknown" "not in allowlist — audit mode: allow+log"
    fi
    ;;

  enforce)
    # 白名單正式生效：未命中直接拒絕
    if _in_allowlist "${CMD_TOKEN}"; then
      log_decision "allow" "allowlist" "in allowlist"
    elif _in_observelist "${CMD_TOKEN}"; then
      log_decision "allow" "observe" "in observelist"
    else
      log_decision "deny" "unknown" "not in allowlist — enforce mode: deny"
      echo "[gateway] 拒絕: 命令不在白名單（enforce mode）" >&2
      exit 1
    fi
    ;;

  break-glass)
    # 緊急放寬：允許通過但標記為高風險，同時寫入獨立 log
    log_decision "allow" "break-glass" "BREAK-GLASS MODE — high risk bypass"
    printf '%s | BREAK-GLASS | cmd=%s\n' \
      "$(date '+%Y-%m-%dT%H:%M:%S')" "${REQUESTED_CMD}" \
      >> "${LOG_DIR}/break-glass.log"
    ;;

  *)
    log_decision "deny" "unknown-mode" "unknown GATEWAY_MODE: ${GATEWAY_MODE}"
    echo "[gateway] 拒絕: 未知 GATEWAY_MODE（${GATEWAY_MODE}）" >&2
    exit 1
    ;;

esac

# ── 切換工作目錄 ──────────────────────────────────────────────────────

mkdir -p "${WORKSPACE}"
cd "${WORKSPACE}" || deny "cannot cd to workspace"

# ── 執行命令 ──────────────────────────────────────────────────────────

log "ALLOW" "cmd=${REQUESTED_CMD}"

bash -lc "${REQUESTED_CMD}"
EXIT_CODE=$?

log "DONE " "cmd=${REQUESTED_CMD} exit=${EXIT_CODE}"
exit ${EXIT_CODE}

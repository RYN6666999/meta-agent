#!/usr/bin/env bash
# agent-queue-daemon.sh — jobs/incoming/ 監控 + 自動執行
#
# [OPTIONAL — P7 Lite 非核心路徑]
# P7 Lite 日常主路徑為 CLI 直接執行：scripts/agent-run <job.json>
# 本 daemon 保留作為「自動掃描」備援，非必要不啟動。
# 若需停用：launchctl unload ~/Library/LaunchAgents/com.agentbot.queue-daemon.plist
#
# 設計：
#   - 每 5 秒掃描 jobs/incoming/*.json
#   - 發現後呼叫 runner/src/run-job.ts（一次一個，避免並發衝突）
#   - 不依賴 n8n，與 tg-daemon 互為補充
#
# 部署：
#   sudo cp host/bin/agent-queue-daemon.sh /usr/local/bin/
#   sudo chmod 755 /usr/local/bin/agent-queue-daemon.sh
#   cp host/launchd/com.agentbot.queue-daemon.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.agentbot.queue-daemon.plist

set -uo pipefail

# ── 路徑設定 ──────────────────────────────────────────────────────────

if [[ -n "${AGENT_SSH_GATEWAY_DIR:-}" ]]; then
  PROJECT_DIR="${AGENT_SSH_GATEWAY_DIR}"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

JOBS_INCOMING="${PROJECT_DIR}/jobs/incoming"
RUNNER_DIR="${PROJECT_DIR}/runner"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/queue-daemon.log"
POLL_INTERVAL=5   # 秒

# launchd 不繼承 PATH，直接指向 nvm node 與 ts-node
NODE_BIN="${HOME}/.nvm/versions/node/v20.18.3/bin/node"
TSNODE_BIN="${RUNNER_DIR}/node_modules/.bin/ts-node"
RUN_JOB_TS="${RUNNER_DIR}/src/run-job.ts"

mkdir -p "${LOG_DIR}"

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%S')" "$*" >> "${LOG_FILE}"; }

log "INFO queue-daemon started pid=$$ project=${PROJECT_DIR}"

# ── 主迴圈 ───────────────────────────────────────────────────────────

while true; do
  # 逐一處理 incoming/*.json（glob 展開失敗時跳過）
  shopt -s nullglob
  job_files=( "${JOBS_INCOMING}"/*.json )
  shopt -u nullglob

  for job_file in "${job_files[@]+"${job_files[@]}"}"; do
    job_id="$(basename "${job_file}" .json)"
    log "INFO dispatching job_id=${job_id} file=${job_file}"

    # 執行 runner，工作目錄設為 PROJECT_DIR 確保相對路徑正確
    if (cd "${PROJECT_DIR}" && \
        "${NODE_BIN}" "${TSNODE_BIN}" "${RUN_JOB_TS}" "${job_file}" \
        >> "${LOG_DIR}/runner.log" 2>&1); then
      log "INFO job done job_id=${job_id}"
    else
      rc=$?
      log "WARN job finished with exit=${rc} job_id=${job_id}"
    fi
  done

  sleep "${POLL_INTERVAL}"
done

#!/usr/bin/env bash
# run-job-n8n.sh — n8n Execute Command node 專用薄包裝
#
# 用途：
#   讓 n8n 不必知道 cwd、node/npm 細節與路徑展開。
#   接收 job 檔案路徑（絕對路徑或相對於此 script 的路徑），
#   回傳 exit code 與 result 檔路徑到 stdout。
#
# 用法（在 n8n Execute Command node 填入）：
#   bash /path/to/scripts/run-job-n8n.sh /path/to/jobs/incoming/my-job.json
#
# n8n 讀取結果：
#   完成後從 jobs/done/<id>.result.json 讀取（路徑由本 script 輸出）
#
# Exit codes：
#   與 run-job.ts 一致
#   0 = done, 1 = 參數錯誤, 2 = schema 錯誤, 3 = failed, 4 = auth_expired

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNNER_DIR="$GATEWAY_ROOT/runner"

# ── 參數驗證 ──────────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
  echo "[run-job-n8n] ERROR: 請提供 job 檔案路徑" >&2
  echo "[run-job-n8n] 用法: $0 <job-file.json>" >&2
  exit 1
fi

JOB_FILE="$1"

# 相對路徑轉絕對路徑
if [[ "$JOB_FILE" != /* ]]; then
  JOB_FILE="$(pwd)/$JOB_FILE"
fi

if [[ ! -f "$JOB_FILE" ]]; then
  echo "[run-job-n8n] ERROR: 找不到 job 檔案: $JOB_FILE" >&2
  exit 1
fi

# ── SSH 環境變數（若 runner.config.json 已設定可省略） ─────────────────

# 若 n8n 需要覆寫 SSH 設定，在此處 export 或在 n8n workflow 設 env var
# export SSH_HOST=127.0.0.1
# export SSH_USER=agentbot
# export SSH_KEY_PATH=~/.ssh/agentbot_ed25519

# ── 執行 run-job.ts ──────────────────────────────────────────────────

cd "$RUNNER_DIR"

# 從 job 檔取得 job_id（供 n8n 後續讀取 result 路徑）
JOB_ID=$(node -e "
const fs = require('fs');
const raw = JSON.parse(fs.readFileSync('$JOB_FILE','utf-8'));
console.log(raw.job_id || raw.id || '');
" 2>/dev/null || echo "")

echo "[run-job-n8n] job_id=$JOB_ID"
echo "[run-job-n8n] job_file=$JOB_FILE"

# 執行（npm run run-job 會呼叫 ts-node run-job.ts）
npm run run-job -- "$JOB_FILE"
EXIT_CODE=$?

# ── 輸出 result 路徑（讓 n8n 知道去哪讀） ─────────────────────────────

JOB_FILENAME="$(basename "$JOB_FILE")"
RESULT_FILENAME="${JOB_FILENAME%.json}.result.json"

if [[ $EXIT_CODE -eq 0 ]]; then
  RESULT_PATH="$GATEWAY_ROOT/jobs/done/$RESULT_FILENAME"
  echo "[run-job-n8n] STATUS=done"
  echo "[run-job-n8n] RESULT_PATH=$RESULT_PATH"
elif [[ $EXIT_CODE -eq 4 ]]; then
  RESULT_PATH="$GATEWAY_ROOT/jobs/failed/$RESULT_FILENAME"
  echo "[run-job-n8n] STATUS=auth_expired" >&2
  echo "[run-job-n8n] RESULT_PATH=$RESULT_PATH"
else
  RESULT_PATH="$GATEWAY_ROOT/jobs/failed/$RESULT_FILENAME"
  echo "[run-job-n8n] STATUS=failed" >&2
  echo "[run-job-n8n] RESULT_PATH=$RESULT_PATH"
fi

exit $EXIT_CODE

#!/usr/bin/env bash
# verify-structure.sh — 專案目錄結構驗證
#
# 功能：
#   檢查所有關鍵目錄與檔案是否存在
#   輸出通過/失敗清單與最終結果
#
# 使用方式：
#   bash scripts/verify-structure.sh
#
# Exit codes：
#   0 = 所有檢查通過
#   1 = 至少一項檢查失敗

set -uo pipefail

# ── 顏色輸出 ────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check() {
  local type="$1"  # file | dir
  local path="$2"
  local desc="$3"

  if [[ "${type}" == "dir" && -d "${path}" ]]; then
    echo -e "  ${GREEN}✓${NC} [dir]  ${path}  (${desc})"
    ((PASS++))
  elif [[ "${type}" == "file" && -f "${path}" ]]; then
    echo -e "  ${GREEN}✓${NC} [file] ${path}  (${desc})"
    ((PASS++))
  else
    echo -e "  ${RED}✗${NC} [${type}] ${path}  (${desc}) — 不存在"
    ((FAIL++))
  fi
}

# ── 從腳本位置找到專案根目錄 ────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

echo ""
echo "=== AI Agent SSH Gateway — 專案結構驗證 ==="
echo "專案根目錄: ${PROJECT_ROOT}"
echo ""

echo "── 頂層檔案 ──"
check file "${PROJECT_ROOT}/.gitignore"      "排除敏感檔案"
check file "${PROJECT_ROOT}/README.md"       "專案說明"

echo ""
echo "── auth/ ──"
check dir  "${PROJECT_ROOT}/auth"             "auth state 目錄"
check file "${PROJECT_ROOT}/auth/.gitignore" "auth 目錄保護"
check file "${PROJECT_ROOT}/auth/.gitkeep"   "目錄佔位"

echo ""
echo "── jobs/ ──"
check dir  "${PROJECT_ROOT}/jobs/incoming"   "待執行 job"
check dir  "${PROJECT_ROOT}/jobs/running"    "執行中 job"
check dir  "${PROJECT_ROOT}/jobs/done"       "完成 job"
check dir  "${PROJECT_ROOT}/jobs/failed"     "失敗 job"

echo ""
echo "── runner/ ──"
check file "${PROJECT_ROOT}/runner/package.json"    "Node 專案定義"
check file "${PROJECT_ROOT}/runner/tsconfig.json"   "TypeScript 設定"
check file "${PROJECT_ROOT}/runner/src/run-job.ts"          "job 進入點"
check file "${PROJECT_ROOT}/runner/src/refresh-auth.ts"     "auth 更新"
check file "${PROJECT_ROOT}/runner/src/playwright-worker.ts" "web worker"
check file "${PROJECT_ROOT}/runner/src/ssh-worker.ts"        "ssh worker"

echo ""
echo "── host/ ──"
check file "${PROJECT_ROOT}/host/ssh/sshd_config.agentbot.conf" "SSH 設定模板"
check file "${PROJECT_ROOT}/host/bin/agent-gateway.sh"           "命令 gateway"
check file "${PROJECT_ROOT}/host/bin/agent-switch"               "SSH 開關"

echo ""
echo "── scripts/ ──"
check file "${PROJECT_ROOT}/scripts/verify-structure.sh" "本驗證腳本"

# ── 結果 ────────────────────────────────────────────────────
echo ""
echo "============================================"
echo -e "結果: ${GREEN}通過 ${PASS}${NC} / ${RED}失敗 ${FAIL}${NC}"
echo "============================================"
echo ""

if [[ ${FAIL} -gt 0 ]]; then
  echo -e "${RED}有 ${FAIL} 項檢查失敗，請確認目錄結構。${NC}"
  exit 1
else
  echo -e "${GREEN}所有檢查通過！專案骨架完整。${NC}"
  exit 0
fi

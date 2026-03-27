#!/usr/bin/env bash
# diagnose-n8n-p6.sh — P6 n8n 整合環境診斷腳本
# 執行：bash scripts/diagnose-n8n-p6.sh

set -uo pipefail

PASS="✅"; FAIL="❌"; WARN="⚠️ "
errors=0

check() {
  local label="$1"; local cmd="$2"
  if eval "$cmd" &>/dev/null; then
    echo "$PASS $label"
  else
    echo "$FAIL $label"
    ((errors++)) || true
  fi
}

check_output() {
  local label="$1"; local cmd="$2"; local expect="$3"
  local out; out=$(eval "$cmd" 2>&1)
  if echo "$out" | grep -q "$expect"; then
    echo "$PASS $label"
  else
    echo "$FAIL $label  (got: $(echo "$out" | head -1))"
    ((errors++)) || true
  fi
}

echo "======================================================"
echo " P6 n8n 整合環境診斷"
echo "======================================================"

# ── 1. n8n 容器狀態 ──────────────────────────────────────
echo ""
echo "── 1. n8n 容器 ──"
check        "n8n 容器正在執行" \
  "docker ps --filter name=n8n --filter status=running | grep -q n8n"

check_output "n8n API 可達 (port 5678)" \
  "curl -s -o /dev/null -w '%{http_code}' http://localhost:5678/" \
  "200\|301\|302"

# ── 2. volume mount ───────────────────────────────────────
echo ""
echo "── 2. Volume Mount ──"
check        "jobs/ 目錄掛入容器" \
  "docker exec n8n sh -c 'test -d /workspace/agent-ssh-gateway/jobs'"

check        "runner/ 目錄掛入容器" \
  "docker exec n8n sh -c 'test -d /workspace/agent-ssh-gateway/runner'"

check        "SSH key 掛入容器" \
  "docker exec n8n sh -c 'test -f /home/node/.ssh/agentbot_ed25519'"

check        "SSH key 權限正確 (非 world-readable)" \
  "docker exec n8n sh -c 'perm=\$(stat -c %a /home/node/.ssh/agentbot_ed25519 2>/dev/null || stat -f %Lp /home/node/.ssh/agentbot_ed25519); [ \"\$perm\" = \"600\" ] || [ \"\$perm\" = \"400\" ]'"

check        "N8N_RESTRICT_FILE_ACCESS_TO 包含 workspace" \
  "docker exec n8n sh -c 'echo \$N8N_RESTRICT_FILE_ACCESS_TO | grep -q workspace'"

# ── 3. 容器內執行環境 ─────────────────────────────────────
echo ""
echo "── 3. 容器內執行環境 ──"
check        "容器內有 node" \
  "docker exec n8n sh -c 'which node'"

check        "容器內有 npm" \
  "docker exec n8n sh -c 'which npm'"

check        "runner node_modules/ts-node 存在" \
  "docker exec n8n sh -c 'test -f /workspace/agent-ssh-gateway/runner/node_modules/.bin/ts-node'"

check        "runner package.json 有 run-job script" \
  "docker exec n8n sh -c 'cat /workspace/agent-ssh-gateway/runner/package.json | grep -q run-job'"

# ── 4. SSH 連線（容器 → host） ────────────────────────────
echo ""
echo "── 4. SSH 連線（container → host.docker.internal）──"
check        "host.docker.internal 可解析" \
  "docker exec n8n sh -c 'getent hosts host.docker.internal || nslookup host.docker.internal 2>/dev/null'"

check        "SSH port 22 可達 host" \
  "docker exec n8n sh -c 'nc -z -w3 host.docker.internal 22'"

check_output "agentbot SSH 登入成功" \
  "docker exec n8n sh -c 'ssh -i /home/node/.ssh/agentbot_ed25519 -o StrictHostKeyChecking=no -o ConnectTimeout=5 agentbot@host.docker.internal echo SSH_OK 2>&1'" \
  "SSH_OK"

# ── 5. n8n workflow 存在 ──────────────────────────────────
echo ""
echo "── 5. n8n Workflow ──"
NEW_WF_ID="YGl4WZzBhrtNrZPm"
check_output "新 workflow (${NEW_WF_ID}) 存在" \
  "curl -s http://localhost:5678/api/v1/workflows/${NEW_WF_ID} -H 'accept: application/json' 2>/dev/null" \
  "SSH Gateway"

OLD_WF_ID="bJPuC5jiAAwkfMS2"
if curl -s http://localhost:5678/api/v1/workflows/${OLD_WF_ID} 2>/dev/null | grep -q "SSH Gateway"; then
  echo "$WARN 舊 workflow (${OLD_WF_ID}) 仍存在 → 瀏覽器重新整理並切換到新 workflow"
else
  echo "$PASS 舊 workflow (${OLD_WF_ID}) 已刪除"
fi

# ── 6. jobs 目錄可寫 ──────────────────────────────────────
echo ""
echo "── 6. jobs 目錄讀寫 ──"
check        "容器內可寫 jobs/incoming/" \
  "docker exec n8n sh -c 'touch /workspace/agent-ssh-gateway/jobs/incoming/.write_test && rm /workspace/agent-ssh-gateway/jobs/incoming/.write_test'"

check        "容器內可讀 jobs/done/" \
  "docker exec n8n sh -c 'test -d /workspace/agent-ssh-gateway/jobs/done'"

# ── 結果 ──────────────────────────────────────────────────
echo ""
echo "======================================================"
if [ "$errors" -eq 0 ]; then
  echo "$PASS 全部通過。"
  echo ""
  echo "  下一步：開瀏覽器前往："
  echo "  http://localhost:5678/workflow/${NEW_WF_ID}"
  echo "  點 'Test workflow' 執行。"
else
  echo "$FAIL 發現 ${errors} 個問題，請依上方 ❌ 項目修復。"
fi
echo "======================================================"

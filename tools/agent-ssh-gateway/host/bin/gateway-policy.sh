#!/usr/bin/env bash
# gateway-policy.sh — P7 Lite 命令治理設定檔
#
# 部署位置：/usr/local/bin/gateway-policy.sh（與 agent-gateway.sh 同目錄）
# 用途：被 agent-gateway.sh source，集中管理規則
#
# P7 Lite：固定 enforce 模式，只保留 2 層治理：
#   Layer 1 — HARD_DENY（永遠擋）
#   Layer 2 — ALLOWLIST（只允許白名單）
#
# 日常維護只需修改 ALLOWLIST。

# ── 硬拒絕（Layer 1 — 永遠擋）────────────────────────────────────────
#
# 格式：extended regex，match 命令任意位置（防管線繞過）
#
HARD_DENY=(
  # 提權
  '(^|[[:space:]|;`$])sudo([[:space:]]|$)'
  '(^|[[:space:]|;`$])su([[:space:]]|$)'
  # 二次遠端
  '(^|[[:space:]|;`])ssh([[:space:]]|$)'
  '(^|[[:space:]|;`])scp([[:space:]]|$)'
  '(^|[[:space:]|;`])sftp([[:space:]]|$)'
  '(^|[[:space:]|;`])nc([[:space:]]|$)'
  '(^|[[:space:]|;`])ncat([[:space:]]|$)'
  '(^|[[:space:]|;`])socat([[:space:]]|$)'
  # 危險下載執行
  'curl[^|]*\|[[:space:]]*(ba)?sh'
  'wget[^|]*\|[[:space:]]*(ba)?sh'
  # 破壞性刪除（只擋系統路徑，workspace 下允許）
  'rm[[:space:]].*[[:space:]]+/([[:space:]]|$)'
  'rm[[:space:]].*[[:space:]]+/(etc|boot|System|usr|private|bin|sbin|var/root)(/|[[:space:]]|$)'
  # 系統破壞
  '(^|[[:space:]])reboot([[:space:]]|$)'
  '(^|[[:space:]])shutdown([[:space:]]|$)'
  '(^|[[:space:]])halt([[:space:]]|$)'
  '(^|[[:space:]])poweroff([[:space:]]|$)'
  '(^|[[:space:]])mkfs[[:space:]]'
  'dd[[:space:]]+if='
  # 互動 shell
  'bash[[:space:]]+-i'
  'sh[[:space:]]+-i'
  'zsh[[:space:]]+-i'
  # 系統路徑寫入
  '>[[:space:]]*/etc/'
  '>[[:space:]]*/boot/'
  # 系統設定工具
  '(^|[[:space:]])launchctl([[:space:]]|$)'
  '(^|[[:space:]])dscl([[:space:]]|$)'
  '(^|[[:space:]])passwd([[:space:]]|$)'
)

# ── 允許清單（Layer 2 — 只允許此清單內命令）──────────────────────────
#
# 以命令第一個 token（basename）精確比對。
# 不在此清單內的命令一律拒絕。
#
ALLOWLIST=(
  # 基本查看
  "echo"
  "date"
  "pwd"
  "ls"
  "cat"
  "grep"
  "find"
  "which"
  "env"
  "printenv"
  # 檔案操作（workspace 安全路徑下使用）
  "mkdir"
  "mv"
  "cp"
  "touch"
  "rm"
  "chmod"
  "chown"
  # 文字處理
  "sed"
  "awk"
  "jq"
  "tee"
  "xargs"
  # 開發工具
  "node"
  "npm"
  "npx"
  "python3"
  "git"
  # 下載（不允許 pipe to shell，已由 HARD_DENY 擋）
  "curl"
  "wget"
  # 封存
  "tar"
  "unzip"
  "zip"
  # Shell 執行（非互動式，已由 HARD_DENY 擋互動式）
  "bash"
  "sh"
  # 輔助
  "true"
  "false"
  "test"
  "["
  "sleep"
  "cd"
)

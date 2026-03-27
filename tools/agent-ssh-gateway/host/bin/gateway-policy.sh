#!/usr/bin/env bash
# gateway-policy.sh — P7 命令治理設定檔
#
# 部署位置：/usr/local/bin/gateway-policy.sh（與 agent-gateway.sh 同目錄）
# 用途：被 agent-gateway.sh source，集中管理模式與規則
#
# 修改此檔即可切換模式或調整規則，不需改主腳本。
# 切換模式也可用：agent-switch mode <legacy-blacklist|audit|enforce|break-glass>

# ── 模式選擇 ──────────────────────────────────────────────────────────
#
# legacy-blacklist : 舊黑名單行為（相容模式，緊急回退點）
# audit            : 白名單觀察期；未命中允許但強制記錄（預設上線模式）
# enforce          : 白名單正式生效；未命中直接拒絕
# break-glass      : 緊急放寬；記錄為高風險事件，不作常態模式
#
GATEWAY_MODE="audit"

# ── 硬拒絕（Layer 1 — 永遠擋，不論 GATEWAY_MODE）─────────────────────
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
  # 破壞性刪除（只擋系統路徑和根目錄，workspace 下允許 rm -rf）
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

# ── 正式允許（Layer 2 — allowlist）───────────────────────────────────
#
# 以命令第一個 token（basename）精確比對。
# 依據 runner / n8n job lifecycle 實際需要的最小命令集。
#
ALLOWLIST=(
  "echo"
  "date"
  "pwd"
  "ls"
  "cat"
  "grep"
  "find"
  "mkdir"
  "mv"
  "cp"
  "touch"
  "rm"
  "chmod"
  "chown"
  "cd"
  "env"
  "printenv"
  "which"
  "node"
  "npm"
  "npx"
  "bash"
  "sh"
  "true"
  "false"
  "test"
  "["
  "sleep"
)

# ── 觀察中（Layer 3 — observelist）──────────────────────────────────
#
# 目前風險或必要性尚未確定；audit / enforce 模式都允許通過，但標記為 observe。
# 待觀察期結束後，依 log 分析結果移入 ALLOWLIST 或 HARD_DENY。
#
OBSERVELIST=(
  "python3"
  "python"
  "jq"
  "curl"
  "wget"
  "git"
  "tar"
  "unzip"
  "zip"
  "sed"
  "awk"
  "tee"
  "xargs"
)

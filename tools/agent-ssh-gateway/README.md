# AI Agent SSH Gateway Prototype

個人自用、實驗性質的 AI Agent 受控執行環境。

---

## 專案目的

讓 AI agent 能夠：
1. **操作已登入狀態的網頁**，不需每次重新登入（Playwright auth state）
2. **透過 SSH 執行受限終端命令**，不給完整 shell（OpenSSH gateway）

設計原則：單機、低門檻、最小可行、易回滾。

---

## 架構簡述

```
AI Agent
  │
  ├─► Job Runner (TypeScript)
  │     ├─ web job  → playwright-worker → 使用已儲存的 auth state
  │     └─ ssh job  → ssh-worker → SSH Gateway
  │
  └─► SSH Gateway (OpenSSH + shell)
        └─ agent-gateway.sh（P7 分級命令治理）
               ↑ source
        gateway-policy.sh（mode + allow/observe/deny 規則）
               ↑
        agent-switch（on/off/mode 開關）
```

---

## 目錄說明

```
project/
  auth/                   # Playwright auth state（不入庫）
  jobs/
    incoming/             # 待執行的 job JSON
    running/              # 執行中的 job（runner 移入）
    done/                 # 已完成的 job
    failed/               # 失敗的 job
  runner/                 # TypeScript job runner
    src/
      run-job.ts          # 進入點，讀取 job JSON 並分派
      refresh-auth.ts     # 手動登入並儲存 auth state
      playwright-worker.ts# 執行 web job
      ssh-worker.ts       # 執行 ssh job
  host/
    ssh/
      sshd_config.agentbot.conf  # SSH 設定片段
    bin/
      agent-gateway.sh    # SSH ForceCommand wrapper，P7 分級命令治理
      gateway-policy.sh   # P7 模式設定 + allow/observe/deny 規則（可熱修改）
      agent-switch        # 啟用/停用/切換 mode 的開關
  scripts/
    verify-structure.sh   # 驗證專案結構完整性
  .gitignore
  README.md
```

---

## Phase 1 — SSH Gateway 部署指南（macOS M1/M2）

### 前置：開啟遠端登入

**系統設定 → 一般 → 共享 → 遠端登入** → 開啟
（或終端機：`sudo systemsetup -setremotelogin on`）

> **重要**：macOS 遠端登入若設為「特定使用者」模式，agentbot 帳號建立後
> 必須手動加入 SSH 允許群組，否則金鑰驗證通過後仍會被系統切斷：
> ```bash
> sudo dseditgroup -o edit -a agentbot -t user com.apple.access_ssh
> ```

---

### 1. 建立 agentbot 帳號

```bash
# 建立使用者（macOS 用 sysadmin 工具）
# 先找一個不衝突的 UniqueID
sudo dscl . -list /Users UniqueID | awk '{print $2}' | sort -n | tail -5

# 以下以 UID=503 為例（請替換為未使用的號碼）
sudo dscl . -create /Users/agentbot
sudo dscl . -create /Users/agentbot UserShell /bin/bash
sudo dscl . -create /Users/agentbot RealName "AI Agent Bot"
sudo dscl . -create /Users/agentbot UniqueID 503
sudo dscl . -create /Users/agentbot PrimaryGroupID 20
sudo dscl . -create /Users/agentbot NFSHomeDirectory /Users/agentbot
sudo createhomedir -c -u agentbot

# 建立必要目錄
sudo mkdir -p /Users/agentbot/.ssh
sudo mkdir -p /Users/agentbot/workspace
sudo mkdir -p /Users/agentbot/logs
sudo chown -R agentbot:staff /Users/agentbot
sudo chmod 700 /Users/agentbot/.ssh
```

### 2. 部署 gateway 腳本

```bash
# 從專案根目錄執行
sudo cp host/bin/agent-gateway.sh  /usr/local/bin/agent-gateway.sh
sudo cp host/bin/gateway-policy.sh /usr/local/bin/gateway-policy.sh
sudo cp host/bin/agent-switch      /usr/local/bin/agent-switch
sudo chmod 755 /usr/local/bin/agent-gateway.sh
sudo chmod 644 /usr/local/bin/gateway-policy.sh
sudo chmod 755 /usr/local/bin/agent-switch
```

> **P7 注意**：`gateway-policy.sh` 必須與 `agent-gateway.sh` 放在同一目錄，
> gateway 啟動時自動 source。若不存在則退回 `legacy-blacklist` 模式。

### 3. 部署 sshd 設定

```bash
# 建立 sshd_config.d 目錄（macOS 預設不存在）
sudo mkdir -p /etc/ssh/sshd_config.d

# 複製設定片段
sudo cp host/ssh/sshd_config.agentbot.conf /etc/ssh/sshd_config.d/agentbot.conf
sudo chmod 644 /etc/ssh/sshd_config.d/agentbot.conf

# 確認 /etc/ssh/sshd_config 有 Include 指令（macOS Ventura+ 預設已有）
grep -n "Include" /etc/ssh/sshd_config
# 若沒有，手動加入：
# echo "Include /etc/ssh/sshd_config.d/*.conf" | sudo tee -a /etc/ssh/sshd_config

# 語法驗證（必做）
sudo sshd -t && echo "✓ 設定語法正確"

# 套用設定（macOS 用 launchctl）
sudo launchctl kickstart -k system/com.openssh.sshd
```

### 4. 配置 authorized_keys

```bash
# 產生 agent 專用金鑰對（在你自己的帳號下）
ssh-keygen -t ed25519 -f ~/.ssh/agentbot_ed25519 -C "agentbot@ai-agent" -N ""

# 查看公鑰
cat ~/.ssh/agentbot_ed25519.pub

# 部署公鑰到 agentbot 帳號
sudo -u agentbot bash -c "
  echo '$(cat ~/.ssh/agentbot_ed25519.pub)' \
    > /Users/agentbot/.ssh/authorized_keys
  chmod 600 /Users/agentbot/.ssh/authorized_keys
"
```

authorized_keys 範例（ForceCommand 已由 sshd_config 強制，此處只放公鑰）：

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx agentbot@ai-agent
```

### 5. 啟用 agent-switch

```bash
sudo agent-switch on
sudo agent-switch status
# 輸出範例：
#   Gateway 開關 : ON
#   Gateway Mode : audit
#   => 狀態：READY
```

---

## 驗證步驟

```bash
# 1. sshd 設定語法
sudo sshd -t && echo "OK"

# 2. gateway 空命令拒絕
sudo -u agentbot /usr/local/bin/agent-gateway.sh
# 預期：[gateway] 拒絕: empty command (interactive shell not allowed)

# 3. gateway flag 關閉拒絕（確認 flag 不存在時）
sudo -u agentbot bash -c 'SSH_ORIGINAL_COMMAND="echo hi" /usr/local/bin/agent-gateway.sh'
# 若 flag 不存在 → [gateway] 拒絕: agent-switch is OFF

# 4. agent-switch on 後測試正常命令
sudo agent-switch on
sudo -u agentbot bash -c 'SSH_ORIGINAL_COMMAND="echo hello" /usr/local/bin/agent-gateway.sh'
# 預期輸出：hello

# 5. 測試 hard-deny 攔截（任何 mode 都擋）
sudo -u agentbot bash -c 'SSH_ORIGINAL_COMMAND="sudo whoami" /usr/local/bin/agent-gateway.sh'
# 預期：[gateway] 拒絕: hard-deny pattern matched

# 6. 真實 SSH 連線測試（本機 loopback）
ssh -i ~/.ssh/agentbot_ed25519 -o StrictHostKeyChecking=no agentbot@127.0.0.1 'echo hello'
# 預期輸出：hello

# 7. 查看 log
sudo tail -20 /Users/agentbot/logs/agent-ssh.log
```

---

## 回滾步驟

```bash
# 快速：關閉開關（gateway 立即拒絕所有命令）
sudo agent-switch off

# 完整回滾
sudo rm -f /usr/local/bin/agent-gateway.sh /usr/local/bin/agent-switch
sudo rm -f /etc/ssh/sshd_config.d/agentbot.conf
sudo sshd -t && sudo launchctl kickstart -k system/com.openssh.sshd

# 刪除 agentbot 帳號（可選）
sudo dscl . -delete /Users/agentbot
sudo rm -rf /Users/agentbot
```

---

## Log 格式（P7）

`/Users/agentbot/logs/agent-ssh.log`：

```
# 決策 log（P7 新增，可 grep decision=/category=）
2026-03-27T10:00:00 | ALLOW | mode=audit decision=allow category=allowlist cmd=echo hello reason=in allowlist
2026-03-27T10:00:01 | ALLOW | mode=audit decision=allow category=unknown cmd=htop reason=not in allowlist — audit mode: allow+log
2026-03-27T10:00:02 | DENY  | mode=enforce decision=deny category=unknown cmd=htop reason=not in allowlist — enforce mode: deny
2026-03-27T10:00:03 | DENY  | mode=audit decision=deny category=hard-deny cmd=sudo ls reason=hard-deny pattern matched: ...

# 執行 log（原有）
2026-03-27T10:00:00 | ALLOW | cmd=echo hello
2026-03-27T10:00:00 | DONE  | cmd=echo hello exit=0
```

`/Users/agentbot/logs/break-glass.log`（break-glass 模式專用）：

```
2026-03-27T10:00:00 | BREAK-GLASS | cmd=some-risky-command
```

### 常用 log 查詢

```bash
# 查所有被拒絕的命令
grep "decision=deny" /Users/agentbot/logs/agent-ssh.log

# 查 audit 觀察期的 unknown commands（未來 allowlist 收斂依據）
grep "category=unknown" /Users/agentbot/logs/agent-ssh.log

# 查目前 mode 的統計
grep -oP 'mode=\S+' /Users/agentbot/logs/agent-ssh.log | sort | uniq -c
```

---

---

## Phase 2 — Playwright Auth State

### 安裝依賴

```bash
cd runner
npm install
npx playwright install chromium   # 下載 Chromium 瀏覽器
```

### 第一次登入（儲存 auth state）

每個網站各自登入一次，之後 agent 自動重用：

```bash
# 格式：SITE=<名稱> LOGIN_URL=<登入頁> npm run refresh-auth

SITE=fundodo    LOGIN_URL=https://fundodo.net/fundodo/          npm run refresh-auth
SITE=github     LOGIN_URL=https://github.com/login              npm run refresh-auth
SITE=cloudflare LOGIN_URL=https://dash.cloudflare.com/login     npm run refresh-auth
SITE=genspark   LOGIN_URL=https://www.genspark.ai               npm run refresh-auth
SITE=google     LOGIN_URL=https://accounts.google.com           npm run refresh-auth
```

瀏覽器開啟後手動完成登入（含 2FA、驗證碼），回終端機按 Enter 儲存。

### Auth 檔案結構

```
auth/
  sites/
    fundodo/
      auth-state.json   ← storageState（cookies + localStorage）
      profile/          ← 完整 browser profile
    github/
      auth-state.json
      profile/
    cloudflare/
      auth-state.json
      profile/
```

### auth-state.json 的用途

Playwright `storageState` 格式，包含 cookies + localStorage。
`WorkerSession.init()` 將其注入新 browser context，等同帶著已登入的瀏覽器執行。

### auth/profile/ 的用途

`launchPersistentContext` 使用的完整 user data 目錄。
`refresh-auth` 兩者都保存；`playwright-worker` 預設只用 `auth-state.json`（較輕量）。

### 為什麼不能提交 auth 檔案到版本庫

- `auth-state.json` 等同登入憑證，外洩即帳號遭接管
- `auth/*/profile/` 可達數百 MB，不適合入庫
- `.gitignore` 已排除整個 `auth/` 目錄

### Session 過期時的處理

`playwright-worker` 每次導頁後比對 `LOGIN_PAGE_PATTERNS`，偵測到登入頁即回傳 `AUTH_EXPIRED`：

```
AUTH_EXPIRED: github session 已過期，請重新執行：
  SITE=github LOGIN_URL=https://github.com/login npm run refresh-auth
```

### Job JSON 格式（web job）

```json
{
  "job_id": "web-001",
  "type": "web",
  "steps": [
    { "kind": "web", "site": "github", "action": "open_page", "url": "https://github.com/dashboard" },
    { "kind": "web", "site": "github", "action": "get_text",  "selector": "h1" }
  ]
}
```

`site` 欄位對應 `auth/sites/` 下的目錄名稱。

---

---

## Phase 3 — Job Runner

### Job JSON 格式

**Web Job**（純網頁操作）：
```json
{
  "job_id": "web-001",
  "type": "web",
  "steps": [
    { "kind": "web", "site": "fundodo", "action": "open_page", "url": "https://fundodo.net/fundodo/" },
    { "kind": "web", "site": "fundodo", "action": "get_text",  "selector": "h1" }
  ]
}
```

**SSH Job**（純終端命令）：
```json
{
  "job_id": "ssh-001",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "echo hello" },
    { "kind": "ssh", "command": "date" }
  ]
}
```

**Hybrid Job**（混合）：
```json
{
  "job_id": "hybrid-001",
  "type": "hybrid",
  "steps": [
    { "kind": "web", "site": "github", "action": "open_page", "url": "https://github.com/dashboard" },
    { "kind": "ssh", "command": "ls -la /Users/agentbot/workspace" }
  ]
}
```

支援的 web action：

| action | 說明 | 必要欄位 |
|--------|------|----------|
| `open_page` | 導覽到指定 URL | `url` |
| `click` | 點擊元素 | `selector` |
| `fill` | 填入文字 | `selector`, `value` |
| `get_text` | 取得元素文字 | `selector` |
| `wait_for` | 等待元素出現 | `selector` |

### 如何提交與執行 Job

```bash
# 1. 將 job JSON 放入 incoming
cp jobs/examples/hybrid-job.json jobs/incoming/hybrid-001.json

# 2. 設定 SSH 環境變數（ssh job 需要）
export SSH_HOST=127.0.0.1
export SSH_USER=agentbot
export SSH_KEY_PATH=~/.ssh/agentbot_ed25519

# 3. 執行
cd runner
npm run run-job -- ../jobs/incoming/hybrid-001.json
```

### Job 生命週期

```
jobs/incoming/<id>.json   → 待執行
jobs/running/<id>.json    → 執行中（runner 移入）
jobs/done/<id>.json       → 成功（含 result 欄位）
jobs/failed/<id>.json     → 失敗（含 error 欄位）
```

### done / failed 判定規則

- **done**：所有 steps 均回傳 `status: ok`
- **failed**：任一 step 回傳 `status: error`，後續 steps 略過
- **auth_expired**（歸入 failed）：web step 偵測到登入頁，job 立即中止

### AUTH_EXPIRED 處理方式

1. job 移至 `jobs/failed/`，result 包含：
   ```json
   { "error": "AUTH_EXPIRED: site=\"github\"，請重新執行 refresh-auth" }
   ```
2. 重新登入：
   ```bash
   SITE=github LOGIN_URL=https://github.com/login npm run refresh-auth
   ```
3. 重新提交 job（複製回 `jobs/incoming/`）

---

## Phase 6 — n8n 整合（Code node 模式）

### 整合方式

n8n workflow 使用單一 **Code node**，透過 Node.js `fs` + `child_process` 完成寫檔、執行、讀取 result 三步驟。

```
n8n workflow
  [Manual Trigger]
  → [Code node]
      1. fs.writeFileSync → jobs/incoming/<id>.json
      2. execSync → npm run run-job（runner 執行 SSH job）
      3. fs.readFileSync → jobs/done/<id>.result.json
      → 回傳 JobResult JSON
```

> **注意**：此版本 n8n（2.36.1 / n8n-with-ffmpeg）的 Execute Command node 無法使用，
> 改以 Code node + `child_process` 取代，行為等效。

### Docker Volume Mount（必要）

n8n 跑在 Docker 時，必須將 gateway 專案目錄與 SSH key 掛入容器。

編輯 `docker-compose.yml`，在 n8n service 加入：

```yaml
services:
  n8n:
    environment:
      - N8N_RESTRICT_FILE_ACCESS_TO=/home/node/.n8n;/home/node/obsidian;/workspace/agent-ssh-gateway
      - NODE_FUNCTION_ALLOW_BUILTIN=child_process,fs,path,os
    volumes:
      - /Users/ryan/meta-agent/tools/agent-ssh-gateway:/workspace/agent-ssh-gateway
      - /Users/ryan/.ssh/agentbot_ed25519:/home/node/.ssh/agentbot_ed25519:ro
```

重啟容器：

```bash
cd /Users/ryan/Projects/n8n
docker compose up -d
```

### Code node 完整程式碼

```javascript
const { execSync } = require('child_process');
const fs = require('fs');

// 產生唯一 job_id
const ts = new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 17);
const jobId = `n8n-ssh-${ts}`;

const job = {
  job_id: jobId,
  type: 'ssh',
  steps: [
    { kind: 'ssh', command: 'date' },
    { kind: 'ssh', command: 'echo n8n_trigger_ok' }
  ]
};

// 寫 job 檔案
const jobPath = `/workspace/agent-ssh-gateway/jobs/incoming/${jobId}.json`;
fs.writeFileSync(jobPath, JSON.stringify(job, null, 2), 'utf-8');

// 執行 runner（容器內 → host.docker.internal SSH）
const env = {
  SSH_HOST: 'host.docker.internal',
  SSH_USER: 'agentbot',
  SSH_KEY_PATH: '/home/node/.ssh/agentbot_ed25519',
  HOME: '/home/node',
  PATH: '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/nvm/versions/node/v22.22.1/bin'
};

try {
  execSync(
    `cd /workspace/agent-ssh-gateway/runner && npm run run-job -- ${jobPath}`,
    { env, timeout: 120000, stdio: 'pipe' }
  );
  const resultPath = `/workspace/agent-ssh-gateway/jobs/done/${jobId}.result.json`;
  return [{ json: JSON.parse(fs.readFileSync(resultPath, 'utf-8')) }];
} catch (err) {
  const failedPath = `/workspace/agent-ssh-gateway/jobs/failed/${jobId}.result.json`;
  if (fs.existsSync(failedPath)) {
    return [{ json: JSON.parse(fs.readFileSync(failedPath, 'utf-8')) }];
  }
  throw new Error(String(err.message || err));
}
```

### SSH 目標主機說明

| 執行環境 | SSH_HOST 設定 |
|---------|--------------|
| n8n 在 Docker | `host.docker.internal`（容器 → host） |
| n8n 在 host mode | `127.0.0.1` |

`host.docker.internal` 需要 docker-compose.yml 設定：
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### result 格式

```json
{
  "job_id": "n8n-ssh-20260327001000000",
  "status": "done",
  "started_at": "2026-03-27T10:00:00.000Z",
  "finished_at": "2026-03-27T10:00:01.234Z",
  "steps": [
    { "kind": "ssh", "status": "ok", "output": { "stdout": "Fri Mar 27 10:00:00 CST 2026\n", "stderr": "" } },
    { "kind": "ssh", "status": "ok", "output": { "stdout": "n8n_trigger_ok\n", "stderr": "" } }
  ]
}
```

### 範例 job 檔案

`jobs/examples/n8n-trigger-job.json`：純 SSH job 範本，可直接複製修改。

---

## Phase 7 — 分級風控升級（Controlled Allowlist Mode）

P7 不以「一次切成嚴格白名單」為目標，而是將 SSH Gateway 升級為四種模式的
分級命令治理框架，在不打壞既有 P6 流程的前提下，逐步從黑名單原型收斂到
可執行、可審計、可回退的白名單控制模式。

### 四種模式

| 模式 | 用途 | 切換命令 |
|------|------|---------|
| `legacy-blacklist` | 舊黑名單行為，緊急回退點 | `agent-switch mode legacy-blacklist` |
| `audit` | **預設**：未知命令允許但強制記錄，用於觀察期 | `agent-switch mode audit` |
| `enforce` | 未知命令直接拒絕，正式白名單模式 | `agent-switch mode enforce` |
| `break-glass` | 緊急放寬，記錄高風險事件，不作常態 | `agent-switch mode break-glass` |

### 命令分層

| 層 | 名稱 | 行為 |
|----|------|------|
| Layer 1 | Hard Deny | 永遠擋（sudo、ssh、curl\|sh 等） |
| Layer 2 | Allowlist | 明確允許（echo、date、ls、npm 等） |
| Layer 3 | Observelist | 觀察中（jq、curl、git 等），audit/enforce 允許通過但標記 |
| Layer 4 | Unknown | audit 允許+記錄，enforce 拒絕 |

### 模式切換

```bash
# 查目前模式
agent-switch status

# 切換模式
agent-switch mode audit            # 回到觀察期（預設）
agent-switch mode enforce          # 收緊：未知命令拒絕
agent-switch mode legacy-blacklist # 緊急回退
agent-switch mode break-glass      # 緊急放寬（臨時）
```

### enforce 的切換門檻

只有在以下條件全部達成後才應切換至 `enforce` 作為正式預設：
- 最近 N 輪真實 job 沒有新的 `category=unknown` 出現
- ssh-only / n8n trigger / hybrid 驗收全過
- rollback 演練已執行過一次

### 誤擋時的 rollback 順序

```bash
# 1. 先恢復可用性（不要在故障中 debug 規則）
sudo agent-switch mode audit         # 或
sudo agent-switch mode legacy-blacklist

# 2. 查 log 找誤擋原因
grep "decision=deny" /Users/agentbot/logs/agent-ssh.log | tail -20

# 3. 把命令移入 gateway-policy.sh 的 ALLOWLIST（不改主腳本）
# 4. 再視情況切回 enforce
```

---

## Phases 進度

| Phase | 目標 | 狀態 |
|-------|------|------|
| Phase 0 | 專案骨架 | ✅ 完成 |
| Phase 1 | SSH Gateway 最小可用版（黑名單 + 開關 + log） | ✅ 完成 |
| Phase 2 | Playwright auth state 登入與重用 | ✅ 完成 |
| Phase 3 | Job Runner 完整實作（web + ssh hybrid） | ✅ 完成 |
| Phase 4 | Runner 整合 SSH job | ✅ 完成（併入 Phase 3） |
| Phase 5 | Log 規範與錯誤處理 | ✅ 完成 |
| Phase 6 | n8n Job Trigger 整合（Execute Command 模式） | ✅ 完成 |
| Phase 7 | 分級風控升級（Controlled Allowlist Mode） | ✅ 完成（audit 觀察期中） |

---

## 安全注意事項

- `auth/` 目錄下的所有檔案**不得入版本庫**（.gitignore 已設定）
- SSH 私鑰同樣排除在外
- `agent-gateway.sh` 採四模式分級治理（P7），預設 `audit` 模式
- `audit` 模式：未知命令允許通過但記錄，適合觀察期與日常操作
- `enforce` 模式：未知命令直接拒絕，切換前請確認 allowlist 完整
- `agent-switch off` 可立即切斷 AI agent 的 SSH 存取
- 規則調整只需修改 `gateway-policy.sh`，不需改主腳本
- `legacy-blacklist` 模式保留為緊急回退點

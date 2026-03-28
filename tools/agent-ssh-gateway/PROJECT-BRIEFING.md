# AI Agent SSH Gateway — 完整技術報告

> 版本：2026-03-28
> 用途：提供給其他 AI 作為技術背景參考
> 專案路徑：`/Users/ryan/meta-agent/tools/agent-ssh-gateway/`

---

## 一、專案定位

**個人用、單機部署、實驗性質的 AI Agent 受控執行環境。**

讓 AI agent（n8n workflow / 直接 CLI 呼叫）能夠：
1. **透過 SSH 執行受限 shell 命令** — 不給完整 shell，透過 gateway 過濾
2. **操作已登入狀態的網頁** — 用 Playwright 重用 auth state，不需每次重新登入
3. **混合執行** — 一個 job 可以交替執行 web 操作和 SSH 命令

設計原則：**單機、低門檻、最小可行、易回滾。**

---

## 二、技術棧

| 層級 | 技術 | 版本/說明 |
|------|------|-----------|
| **Job Runner** | TypeScript + ts-node | Node.js v20 |
| **Web 自動化** | Playwright | chromium headless |
| **SSH 執行** | OpenSSH client（`spawn("ssh")`） | Node.js child_process |
| **Gateway 過濾** | Bash shell script | ForceCommand on macOS |
| **Queue 管理** | Bash daemon + launchd | 每 5 秒掃 incoming/ |
| **Telegram 通知** | Bash curl（getUpdates long-poll） | bot token + chat_id |
| **n8n 整合** | Docker + Code node（child_process） | n8n 2.36.1 |
| **常駐服務** | macOS launchd | ~/Library/LaunchAgents/ |
| **作業系統** | macOS M2（Ventura+） | sysadmin/dscl/launchctl |

---

## 三、整體架構

```
╔══════════════════════════════════════════════════════════════╗
║                        觸發層                                 ║
║  n8n workflow (Docker)   |   Telegram Bot   |   直接 CLI     ║
╚══════════════════════════════════════════════════════════════╝
                           │
                    Job JSON 丟進
                   jobs/incoming/
                           │
╔══════════════════════════╧═══════════════════════════════════╗
║                    Queue Daemon                               ║
║   agent-queue-daemon.sh（launchd，每 5 秒掃 incoming/）      ║
╚══════════════════════════╤═══════════════════════════════════╝
                           │
╔══════════════════════════╧═══════════════════════════════════╗
║                    Job Runner（TypeScript）                   ║
║  run-job.ts                                                   ║
║    ├─ web step  → playwright-worker.ts → auth/sites/<site>/  ║
║    └─ ssh step  → ssh-worker.ts → SSH → agent-gateway.sh     ║
╚══════════════════════════════════════════════════════════════╝
                                          │
╔═════════════════════════════════════════╧════════════════════╗
║                    SSH Gateway（Bash）                        ║
║  agent-gateway.sh（ForceCommand）                             ║
║    ← source ─ gateway-policy.sh（mode + 三層規則）           ║
║  agent-switch（on/off/mode 開關）                             ║
╚══════════════════════════════════════════════════════════════╝
                           │
╔══════════════════════════╧═══════════════════════════════════╗
║                    Telegram 雙向通道                          ║
║  agent-tg-daemon.sh（launchd，getUpdates long-poll）         ║
║  /status /jobs /requeue /help                                 ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 四、核心模組說明

### 4.1 Job Runner（`runner/src/run-job.ts`）

- **進入點**：`npm run run-job -- <job-file.json>`
- 讀取 job JSON → 移至 `running/` → 依序執行 steps → 移至 `done/` 或 `failed/`
- 同時寫 `<id>.json`（job 定義）和 `<id>.result.json`（執行結果）
- 整個 job 有 timeout 保護（`jobTimeoutMs`，預設 120 秒）
- AUTH_EXPIRED 用自定義 `AuthExpiredError` class，不依賴字串匹配
- 結構化 log 寫入 `logs/runner.log`（JSON Lines 格式）

### 4.2 SSH Worker（`runner/src/ssh-worker.ts`）

- 用 Node.js `child_process.spawn("ssh", [...args])` 呼叫系統 ssh
- `-o BatchMode=yes`：禁止密碼互動，金鑰驗證失敗即 fail
- 設定來源優先順序：env var > runner.config.json

### 4.3 Playwright Worker（`runner/src/playwright-worker.ts`）

- 每個網站各自維護 `auth-state.json`（Playwright storageState）
- `WorkerSession.init()` 將 storageState 注入新 context，等同帶著已登入狀態的瀏覽器
- 每次 `open_page` 後比對 URL pattern，偵測是否被導向登入頁（`AUTH_EXPIRED`）
- 支援 5 種 action：`open_page / click / fill / get_text / wait_for`

### 4.4 SSH Gateway（`host/bin/agent-gateway.sh`）

- **機制**：sshd `ForceCommand` — agentbot 帳號 SSH 進來一定跑這個腳本
- 開關：檢查 `/Users/agentbot/.ssh/enabled.flag`，不存在則拒絕所有命令
- 命令過濾：source 同目錄的 `gateway-policy.sh`（P7 四模式）
- 決策後用 `bash -lc "<command>"` 執行，回傳原始 exit code
- Log rotation：超過 512KB 自動輪轉，保留 3 份

### 4.5 Gateway Policy（`host/bin/gateway-policy.sh`）

四模式：

| 模式 | 行為 | 目前狀態 |
|------|------|----------|
| `legacy-blacklist` | 舊黑名單，緊急回退 | 備用 |
| `audit` | 未知命令允許+記錄 | 觀察期用 |
| `enforce` | 未知命令直接拒絕 | **目前模式** |
| `break-glass` | 緊急放寬，高風險記錄 | 救火用 |

三層規則：
- **HARD_DENY**（Layer 1）：永遠擋，不論模式。包含 sudo/su、ssh/scp/sftp、curl|sh、rm / 系統路徑、reboot/shutdown、bash -i、寫入 /etc
- **ALLOWLIST**（Layer 2）：echo/date/ls/cat/grep/find/mkdir/mv/cp/touch/rm/chmod/node/npm/npx/bash/sh 等
- **OBSERVELIST**（Layer 3）：python3/jq/curl/wget/git/tar/sed/awk 等，audit+enforce 都允許，但標記為 observe

### 4.6 Queue Daemon（`host/bin/agent-queue-daemon.sh`）

- launchd 常駐，每 5 秒掃 `jobs/incoming/`
- 發現 .json 即呼叫 ts-node run-job.ts
- 序列執行（一次一個 job，避免並發衝突）
- 解決 n8n 無法自動 re-queue 的問題

### 4.7 Telegram Daemon（`host/bin/agent-tg-daemon.sh`）

- launchd 常駐，curl getUpdates long-poll（timeout=30s）
- 只接受白名單 chat_id，其他靜默丟棄
- 支援指令：`/status` `/jobs` `/requeue <job_id>` `/help`
- `/requeue` 只顯示 cp 指令，不自動執行（人工確認）
- job_id 注入防護：regex 驗證 `^[a-zA-Z0-9_-]+$`
- 唯讀 grep gateway-policy.sh，不 source

---

## 五、Job 格式

```json
{
  "job_id": "hybrid-20260327-001",
  "type": "web | ssh | hybrid",
  "steps": [
    { "kind": "web", "site": "github", "action": "open_page", "url": "https://github.com/dashboard" },
    { "kind": "web", "site": "github", "action": "get_text",  "selector": "h1" },
    { "kind": "ssh", "command": "date" }
  ]
}
```

Result 格式：
```json
{
  "job_id": "hybrid-20260327-001",
  "status": "done | failed | auth_expired",
  "started_at": "2026-03-27T10:00:00.000Z",
  "finished_at": "2026-03-27T10:00:01.234Z",
  "steps": [
    { "kind": "ssh", "status": "ok", "output": { "stdout": "...", "stderr": "" } }
  ],
  "error": "（job 層錯誤，選填）"
}
```

---

## 六、設定檔（`runner/runner.config.json`）

```json
{
  "ssh": {
    "host": "127.0.0.1",
    "user": "agentbot",
    "keyPath": "~/.ssh/agentbot_ed25519",
    "port": 22,
    "strictHostKeyChecking": "accept-new",
    "connectTimeoutSec": 10
  },
  "sites": {
    "fundodo":    { "loginUrl": "https://fundodo.net/fundodo/" },
    "github":     { "loginUrl": "https://github.com/login" },
    "cloudflare": { "loginUrl": "https://dash.cloudflare.com/login" },
    "genspark":   { "loginUrl": "https://www.genspark.ai" },
    "google":     { "loginUrl": "https://accounts.google.com" }
  },
  "runner": {
    "jobTimeoutMs": 120000
  },
  "authNotify": {
    "webhookUrl": "http://localhost:5678/webhook/auth-expired",
    "timeoutMs": 5000
  }
}
```

---

## 七、Exit Code 規格

### run-job.ts
| Code | 意義 |
|------|------|
| 0 | Job 完成 |
| 1 | 參數錯誤（缺少 job 檔案） |
| 2 | Job JSON 格式錯誤 |
| 3 | Job 執行失敗 |
| 4 | AUTH_EXPIRED |

### agent-gateway.sh
| Code | 意義 |
|------|------|
| 0 | 命令執行成功 |
| 1 | 命令被拒絕 / 開關關閉 / 空命令 |
| N | 被執行命令的原始 exit code |

---

## 八、n8n 整合說明

**n8n 版本**：2.36.1（n8n-with-ffmpeg Docker image）
**整合方式**：Code node + `child_process`（Execute Command node 在此版本無法使用）

```javascript
// Code node 模式
const { execSync } = require('child_process');
const fs = require('fs');
// 1. 寫 job JSON → jobs/incoming/<id>.json
// 2. execSync npm run run-job（同步等待）
// 3. 讀 jobs/done/<id>.result.json 回傳
```

**Docker 環境變數必要設定**：
```yaml
N8N_RESTRICT_FILE_ACCESS_TO: /home/node/.n8n;/workspace/agent-ssh-gateway
NODE_FUNCTION_ALLOW_BUILTIN: child_process,fs,path,os
```

**容器 SSH host 問題**：
n8n 在 Docker 容器內，`127.0.0.1` 指向容器自身。必須用 `host.docker.internal`（搭配 `extra_hosts: host.docker.internal:host-gateway`）。

---

## 九、能力邊界

### 目前可以做

| 能力 | 說明 |
|------|------|
| 執行白名單 shell 命令 | echo/ls/date/node/npm/grep/cat/rm（workspace 內）等 |
| 操作已登入的網頁 | open_page / click / fill / get_text / wait_for |
| 混合 web+ssh job | 一個 job 交替執行兩種步驟 |
| 自動排隊執行 | 丟 JSON 進 incoming/，queue-daemon 自動執行 |
| Telegram 遠端查詢 | /status /jobs /requeue（顯示指令，不自動執行） |
| AUTH_EXPIRED 通知 | 偵測到登入過期，自動 POST n8n webhook 發 Telegram 通知 |
| 緊急開關 | `agent-switch off` 立即斷開 AI SSH 存取 |
| 模式切換 | enforce/audit/break-glass/legacy-blacklist 熱切換 |

### 明確不支援

| 限制 | 原因 |
|------|------|
| 互動式 shell | ForceCommand 阻擋，設計如此 |
| sudo / 提權 | HARD_DENY，永遠擋 |
| 多主機 SSH | 目前 runner.config.json 只有一組 target（P9 Draft） |
| Telegram 自動 re-queue | /requeue 只顯示指令，需人工 cp 確認 |
| web job 自動重登 | AUTH_EXPIRED 後需人工 refresh-auth，自動化有 2FA/鎖帳風險 |
| n8n Telegram Trigger | 需 HTTPS，本地 n8n 不適用，改用 polling daemon |
| callback_url push | P6.5 Draft，升級條件未觸發（長任務卡 n8n） |
| Windows/Linux 部署 | 使用 macOS 特定指令（dscl、launchctl、stat -f%z） |

---

## 十、已解決的 Bug 清單

### B1 — bash 3.2 mapfile 不相容（Session 4）
**症狀**：tg-daemon 在 macOS 起不來，`mapfile` 指令找不到
**原因**：macOS 預設 bash 3.2（2007），`mapfile` 是 bash 4+ 才有的指令
**修復**：將所有 `mapfile -t arr < <(...)` 改為 `while read -r line; do arr+=("$line"); done < <(...)`

### B2 — Gateway: UNKNOWN 誤報（Session 4）
**症狀**：tg-daemon `/status` 顯示 `Gateway: UNKNOWN`
**原因**：`/Users/agentbot/.ssh/` 是 `drwx------`，非 agentbot 身份（ryan）無法讀取 `enabled.flag`
**修復**：改用 `ssh -o BatchMode=yes agentbot@127.0.0.1 'echo ok'` 真實連線測試，以連通性作為 gateway 狀態依據

### B3 — incoming stuck jobs 不執行（Session 4）
**症狀**：job JSON 放進 `incoming/` 後沒有任何反應，永遠卡著
**原因**：沒有持續監控 incoming/ 的機制；原本設計是 n8n 觸發後同步執行，但 n8n 掛掉時 queue 就卡死
**修復**：新增獨立的 `agent-queue-daemon.sh`（launchd 常駐），每 5 秒掃 incoming/ 自動執行，與 n8n 完全解耦

### B4 — queue-daemon set -u 空陣列 crash（Session 4）
**症狀**：queue-daemon 啟動後立即崩潰，log 顯示 `unbound variable`
**原因**：`set -u` 嚴格模式下，空陣列展開 `${arr[@]}` 被視為 unbound variable
**修復**：改用 `${arr[@]+"${arr[@]}"}` 展開語法（空陣列時不展開，有元素時正常展開）

### B5 — rm -rf workspace 被誤擋（P7.1）
**症狀**：`rm -rf /Users/agentbot/workspace/some-dir` 被 HARD_DENY 擋住，job 失敗
**原因**：Phase 1 繼承的 rm pattern 過寬：`rm[[:space:]]+-rf[[:space:]]+` 擋住所有 `-rf` 用法
**修復**：收窄為只擋根目錄和系統路徑：
```
rm[[:space:]].*[[:space:]]+/([[:space:]]|$)
rm[[:space:]].*[[:space:]]+/(etc|boot|System|usr|private|bin|sbin|var/root)(/|[[:space:]]|$)
```
workspace 內的 rm -rf 全部放行

### B6 — n8n Execute Command node 不可用（P6）
**症狀**：建立 Execute Command node 時報錯，node type 不存在
**原因**：此版本 n8n（2.36.1 / n8n-with-ffmpeg）未包含 Execute Command node
**修復**：改用 Code node + Node.js `child_process.execSync`，行為等效

### B7 — n8n 容器 SSH 連不到 host（P6）
**症狀**：n8n Code node 中 `SSH_HOST=127.0.0.1` 連不上，SSH timeout
**原因**：127.0.0.1 在容器內指向容器自身，不是 host 機器
**修復**：改用 `host.docker.internal`，docker-compose.yml 加 `extra_hosts: host.docker.internal:host-gateway`

### B8 — n8n Code node 讀不到 jobs/ 目錄（P6）
**症狀**：`fs.writeFileSync` 失敗，Permission denied
**原因**：`N8N_RESTRICT_FILE_ACCESS_TO` 白名單未包含 agent-ssh-gateway 路徑
**修復**：更新 env var，加入 `/workspace/agent-ssh-gateway`；同時 volume mount 掛入容器

### B9 — n8n Code node 讀不到 process.env（P6）
**症狀**：Code node 裡 `process.env.SSH_HOST` 是 undefined
**原因**：n8n Code node sandbox 不提供 `process` 物件
**修復**：在 Code node 裡硬寫必要 env 變數到 `execSync` 的 `env` 選項

### B10 — sudoers NOPASSWD 部署需要密碼（Session 3）
**症狀**：`sudo cp` 部署腳本到 `/usr/local/bin/` 需要互動輸入密碼
**原因**：agentbot 帳號沒有 NOPASSWD 規則
**修復**：建立 `/etc/sudoers.d/agentbot-deploy`，允許 ryan 免密碼執行特定 cp/chmod 命令

### B11 — agent-switch status 誤報 UNKNOWN（P7.2）
**症狀**：`agent-switch status` 顯示 Gateway 開關 UNKNOWN，讓人以為 off
**原因**：`/Users/agentbot/.ssh/` 是 drwx------，非 agentbot 身份（ryan）無法讀取 enabled.flag
**解決方式（非 bug）**：更新 status 顯示文字為 `UNKNOWN（以真實 SSH 測試確認）`，避免誤導。Gateway 本身功能正常。

---

## 十一、檔案系統結構

```
agent-ssh-gateway/
  auth/
    sites/                    ← 不入庫（.gitignore）
      <site>/
        auth-state.json       ← Playwright storageState
        profile/              ← launchPersistentContext data
  host/
    bin/
      agent-gateway.sh        ← SSH ForceCommand，P7 四模式
      gateway-policy.sh       ← 模式 + 規則設定（可熱修改）
      agent-switch            ← on/off/mode/status 開關
      agent-queue-daemon.sh   ← jobs/incoming/ 監控 daemon
      agent-tg-daemon.sh      ← Telegram 雙向指令 daemon
    launchd/
      com.agentbot.queue-daemon.plist
      com.agentbot.tg-daemon.plist
    ssh/
      sshd_config.agentbot.conf   ← ForceCommand + 限制 forwarding
  jobs/
    incoming/                 ← 放入 → 自動執行
    running/                  ← runner 自動管理
    done/                     ← <id>.json + <id>.result.json
    failed/                   ← <id>.json + <id>.result.json
    examples/                 ← 範本（入庫）
  runner/
    runner.config.json        ← SSH + sites + timeout + authNotify
    src/
      config.ts               ← 設定載入器
      run-job.ts              ← Job Runner 主程式
      refresh-auth.ts         ← 手動登入存 auth state
      playwright-worker.ts    ← WorkerSession（web 步驟）
      ssh-worker.ts           ← runSshCommand（ssh 步驟）
  logs/
    runner.log                ← JSON Lines
    tg-daemon.log
    queue-daemon.log
    agent-ssh.log             ← Gateway 決策 log（在 /Users/agentbot/logs/）
  .secrets.json               ← Telegram token（不入庫）
  SPEC.md                     ← Runtime Contract（已實作的介面）
  DELTA.md                    ← 原計劃 vs 實際落地差異
  FUTURE.md                   ← 未實作的 Draft 設計
```

---

## 十二、常駐服務現況（2026-03-28）

| 服務 | launchd label | 狀態 | 說明 |
|------|---------------|------|------|
| tg-daemon | com.agentbot.tg-daemon | ✅ 運行中 | Telegram getUpdates polling |
| queue-daemon | com.agentbot.queue-daemon | ✅ 運行中 | incoming/ 監控 |
| SSH Gateway | sshd ForceCommand | ✅ enforce 模式 | agentbot 帳號 |

---

## 十三、部署依賴（macOS 特定）

```bash
# agentbot 帳號（系統層）
dscl . -create /Users/agentbot
dseditgroup -o edit -a agentbot -t user com.apple.access_ssh

# sshd ForceCommand
/etc/ssh/sshd_config.d/agentbot.conf
# 內容：ForceCommand /usr/local/bin/agent-gateway.sh
#       AllowStreamLocalForwarding no / GatewayPorts no / AllowAgentForwarding no

# 部署腳本
/usr/local/bin/agent-gateway.sh
/usr/local/bin/gateway-policy.sh
/usr/local/bin/agent-switch
/usr/local/bin/agent-tg-daemon.sh
/usr/local/bin/agent-queue-daemon.sh

# sudoers（免密碼部署）
/etc/sudoers.d/agentbot-deploy
```

---

## 十四、未來 Draft（不需實作，備參考）

| 項目 | 說明 | 觸發條件 |
|------|------|----------|
| P6.5 Callback URL | runner 完成後 POST result 到 n8n webhook | n8n 長任務常卡住 |
| P9 多主機支援 | runner.config 支援多組 SSH target | 有第二台機器 |

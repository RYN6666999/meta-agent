# AI Agent SSH Gateway — P7 Lite

個人自用、最小可用的 AI Agent 受控 SSH 執行環境。

> **單機 · 單人 · 單一入口 · 固定白名單 · 易維護**

---

## 日常主路徑（唯一推薦用法）

```
AI Agent
  │
  └─► scripts/agent-run <job.json>
        │
        └─► runner/src/run-job.ts
              │
              └─► runner/src/ssh-worker.ts
                    │
                    └─► SSH → agentbot@localhost
                              │
                              └─► agent-gateway.sh
                                    ├─ Layer 1: HARD_DENY（永遠擋）
                                    └─ Layer 2: ALLOWLIST（只允許白名單）
```

---

## 快速使用

### 執行一個 SSH job

```bash
# 1. 確認 gateway 已開啟
agent-switch on

# 2. 準備 job JSON
cat > /tmp/my-job.json << 'EOF'
{
  "job_id": "test-001",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "echo hello" },
    { "kind": "ssh", "command": "ls -la" }
  ]
}
EOF

# 3. 執行
./scripts/agent-run /tmp/my-job.json

# 4. 查看結果
cat jobs/done/test-001.result.json
```

### 狀態查看

```bash
agent-switch status   # gateway on/off
agent-status          # 完整狀態（gateway + failed jobs + logs）
```

### 緊急關閉

```bash
agent-switch off      # 立即阻斷所有後續命令
```

---

## 目錄結構

```
agent-ssh-gateway/
  scripts/
    agent-run          # 主要入口（thin wrapper）★
  runner/
    src/
      run-job.ts       # Job runner 進入點 ★
      ssh-worker.ts    # SSH 命令執行 ★
      playwright-worker.ts  # Web automation（optional）
    runner.config.json # SSH 連線設定 ★
  host/
    bin/
      agent-gateway.sh  # SSH ForceCommand（部署到目標主機）★
      gateway-policy.sh # HARD_DENY + ALLOWLIST 規則 ★
      agent-switch      # on/off/status 開關 ★
      agent-status      # 最小狀態檢查 ★
      agent-queue-daemon.sh  # [OPTIONAL] 自動掃描 daemon
      agent-tg-daemon.sh     # [OPTIONAL] Telegram 通知
    launchd/           # launchd plist（optional daemons 用）
    ssh/
      sshd_config.agentbot.conf  # sshd ForceCommand 設定片段
  jobs/
    incoming/          # 放入 job JSON → 手動或 daemon 執行
    running/           # 執行中
    done/              # 完成（含 result）
    failed/            # 失敗（含 result + 錯誤）
    examples/          # Job 範本
  logs/
    runner.log         # Job runner JSON Lines log ★
    (agent-ssh.log 在 /Users/agentbot/logs/)
```

★ = 核心檔案，日常必需

---

## Gateway 治理（2 層）

### Layer 1 — HARD_DENY（永遠擋，不可繞過）
- 提權：`sudo`, `su`
- 二次遠端：`ssh`, `scp`, `sftp`, `nc`, `socat`
- 危險管線：`curl | sh`, `wget | sh`
- 系統破壞：`reboot`, `shutdown`, `mkfs`, `dd if=`
- 互動 shell：`bash -i`, `sh -i`
- 系統路徑寫入：`> /etc/`, `> /boot/`
- 系統設定工具：`launchctl`, `dscl`, `passwd`
- 危險刪除：`rm / ...`, `rm /etc/ ...`

### Layer 2 — ALLOWLIST（只允許以下命令）

| 類別 | 命令 |
|------|------|
| 查看 | echo, date, pwd, ls, cat, grep, find, which, env, printenv |
| 檔案 | mkdir, mv, cp, touch, rm, chmod, chown |
| 文字 | sed, awk, jq, tee, xargs |
| 開發 | node, npm, npx, python3, git |
| 下載 | curl, wget（不允許 pipe to shell） |
| 封存 | tar, unzip, zip |
| Shell | bash, sh（非互動式） |
| 輔助 | true, false, test, [, sleep, cd |

其餘命令一律拒絕。

---

## Job 格式

```json
{
  "job_id": "唯一 ID",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "ls -la" }
  ]
}
```

### 完整結果格式

```json
{
  "job_id": "...",
  "status": "done | failed",
  "started_at": "ISO 8601",
  "finished_at": "ISO 8601",
  "steps": [
    { "kind": "ssh", "status": "ok", "output": { "stdout": "...", "stderr": "" } }
  ]
}
```

---

## 設定

`runner/runner.config.json`：

```json
{
  "ssh": {
    "host": "127.0.0.1",
    "user": "agentbot",
    "keyPath": "~/.ssh/agentbot_ed25519",
    "port": 22
  },
  "runner": {
    "jobTimeoutMs": 120000
  }
}
```

---

## 故障排查

```bash
# Gateway log（命令決策記錄）
tail -50 /Users/agentbot/logs/agent-ssh.log

# Runner log（job 執行記錄，JSON Lines）
tail -50 logs/runner.log

# 最近失敗 job
ls -lt jobs/failed/ | head -10
cat jobs/failed/<id>.result.json

# 確認 gateway 可通
ssh -i ~/.ssh/agentbot_ed25519 agentbot@localhost 'echo ping'
```

### 常見問題

| 症狀 | 原因 | 處理 |
|------|------|------|
| `agent-switch is OFF` | enabled.flag 不存在 | `agent-switch on` |
| `命令不在白名單` | 命令不在 ALLOWLIST | 加入 gateway-policy.sh ALLOWLIST |
| `hard-deny pattern matched` | 命令觸發 HARD_DENY | 不可繞過，請改用其他方式 |
| SSH 連線失敗 | 金鑰或 sshd 設定問題 | 檢查 authorized_keys 和 sshd_config |
| job 卡在 running | runner 異常終止 | 手動 `mv jobs/running/*.json jobs/incoming/` |

---

## 部署（一次性設定）

### 目標主機設定

```bash
# 1. 建立 agentbot 帳號（若未建立）
sudo dscl . -create /Users/agentbot
sudo dscl . -create /Users/agentbot UserShell /bin/bash
# ... （完整步驟見 SPEC.md）

# 2. 部署 gateway 腳本
sudo cp host/bin/agent-gateway.sh /usr/local/bin/
sudo cp host/bin/gateway-policy.sh /usr/local/bin/
sudo cp host/bin/agent-switch /usr/local/bin/
sudo cp host/bin/agent-status /usr/local/bin/
sudo chmod 755 /usr/local/bin/agent-gateway.sh
sudo chmod 755 /usr/local/bin/gateway-policy.sh
sudo chmod 755 /usr/local/bin/agent-switch
sudo chmod 755 /usr/local/bin/agent-status

# 3. 設定 sshd ForceCommand
sudo cp host/ssh/sshd_config.agentbot.conf /etc/ssh/sshd_config.d/agentbot.conf
sudo launchctl kickstart -k system/com.openssh.sshd

# 4. 部署 AI agent 公鑰
# 把 ~/.ssh/agentbot_ed25519.pub 內容加入 /Users/agentbot/.ssh/authorized_keys

# 5. 啟用
agent-switch on
```

### Runner 設定

```bash
cd runner
npm install
# 編輯 runner.config.json（SSH 連線設定）
```

---

## Optional 功能（非必要，可忽略）

| 功能 | 檔案 | 說明 |
|------|------|------|
| 自動掃描 daemon | host/bin/agent-queue-daemon.sh | 監控 jobs/incoming/，自動執行 job |
| Telegram 通知 | host/bin/agent-tg-daemon.sh | /status /jobs 查詢 |
| Web automation | runner/src/playwright-worker.ts | Playwright 網頁操作 |

若需啟用 optional daemon：
```bash
cp host/launchd/com.agentbot.queue-daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.agentbot.queue-daemon.plist
```

---

## 回滾方式

若部署出問題，快速回滾：

```bash
# 立即關閉 gateway（最快，不需改檔案）
agent-switch off

# 或回退舊版 gateway 腳本
sudo cp /usr/local/bin/agent-gateway.sh.bak /usr/local/bin/agent-gateway.sh
sudo cp /usr/local/bin/gateway-policy.sh.bak /usr/local/bin/gateway-policy.sh

# 備份建議（部署前執行）
sudo cp /usr/local/bin/agent-gateway.sh /usr/local/bin/agent-gateway.sh.bak
sudo cp /usr/local/bin/gateway-policy.sh /usr/local/bin/gateway-policy.sh.bak
```

---

## Exit Codes

| Code | 意義 |
|------|------|
| 0 | job 完成 |
| 1 | 參數錯誤或找不到檔案 |
| 2 | job 格式錯誤 |
| 3 | 執行失敗（步驟失敗） |
| 4 | AUTH_EXPIRED（web job 用） |

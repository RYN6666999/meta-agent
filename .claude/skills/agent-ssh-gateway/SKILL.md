---
name: agent-ssh-gateway
description: "Execute controlled local machine commands via SSH Gateway. Use when Claude needs to run multi-step automation, read local state, or execute scripts with audit trail. Provides isolation, allowlist governance, persistent results, and cross-session state."
argument-hint: "[ssh job execution | local automation | read machine state]"
---

# Agent SSH Gateway

## When to Use（觸發條件）

**用 Gateway，不用 Bash tool，當：**
- 多步驟自動化（2 步以上）
- 需要結果跨 session 可查（jobs/done/*.result.json）
- 執行 scripts/ 下的 python3 腳本（bug-closeout、major-change-guard 等）
- 需要審計 log（agent-ssh.log 記錄每筆決策）
- AI 自主執行、Ryan 不在旁邊的時候

**用 Bash tool，不用 Gateway，當：**
- 單次查詢（一行 git status、cat 某檔）
- Claude Code 開發中的即時偵錯
- Ryan 在對話旁確認每一步

---

## 核心路徑

```
gateway 入口   : /Users/ryan/meta-agent/tools/agent-ssh-gateway/scripts/agent-run
job 目錄       : /Users/ryan/meta-agent/tools/agent-ssh-gateway/jobs/
結果目錄       : /Users/ryan/meta-agent/tools/agent-ssh-gateway/jobs/done/
失敗目錄       : /Users/ryan/meta-agent/tools/agent-ssh-gateway/jobs/failed/
gateway log    : /Users/agentbot/logs/agent-ssh.log
runner log     : /Users/ryan/meta-agent/tools/agent-ssh-gateway/logs/runner.log
狀態檢查       : agent-status
開關           : agent-switch on / off
```

---

## Job 格式

```json
{
  "job_id": "唯一ID-日期",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "echo hello" },
    { "kind": "ssh", "command": "ls -la /Users/ryan/meta-agent/" }
  ]
}
```

**規則：**
- `job_id`：唯一，建議格式 `<用途>-<YYYY-MM-DD>`
- `type`：固定 `"ssh"`（P7 Lite 主路徑）
- `steps`：每步一個命令，不要用 `;` 串多個
- 命令必須在 ALLOWLIST 內（否則被 gateway 拒絕，exit 3）

---

## ALLOWLIST 快速參考

可用：`echo date pwd ls cat grep find mkdir mv cp touch rm chmod sed awk jq tee xargs node npm npx python3 git curl wget tar bash sh`

永遠擋：`sudo su ssh scp curl|sh wget|sh rm / reboot shutdown launchctl dscl bash -i`

---

## 執行流程（三步）

### Step 1：寫 job JSON

```bash
cat > /tmp/<job_id>.json << 'EOF'
{
  "job_id": "<job_id>",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "<命令>" }
  ]
}
EOF
```

### Step 2：送 Gateway

```bash
cd /Users/ryan/meta-agent/tools/agent-ssh-gateway
./scripts/agent-run /tmp/<job_id>.json
```

### Step 3：讀結果

```bash
# 成功
cat jobs/done/<job_id>.result.json

# 失敗
cat jobs/failed/<job_id>.result.json
```

---

## 常用場景範本

### 讀機器狀態

```json
{
  "job_id": "machine-status-2026-03-29",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "df -h" },
    { "kind": "ssh", "command": "git -C /Users/ryan/meta-agent log --oneline -5" },
    { "kind": "ssh", "command": "agent-status" }
  ]
}
```

### 跑 meta-agent scripts

```json
{
  "job_id": "truth-xval-2026-03-29",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "python3 /Users/ryan/meta-agent/scripts/truth-xval.py" }
  ]
}
```

### 讀 handoff（跨 session 銜接）

```json
{
  "job_id": "read-handoff-2026-03-29",
  "type": "ssh",
  "steps": [
    { "kind": "ssh", "command": "cat /Users/ryan/meta-agent/memory/handoff/latest-handoff.md" },
    { "kind": "ssh", "command": "cat /Users/ryan/meta-agent/memory/pending-decisions.md" }
  ]
}
```

---

## 結果格式（讀懂 result.json）

```json
{
  "job_id": "...",
  "status": "done",          // done | failed
  "started_at": "...",
  "finished_at": "...",
  "steps": [
    {
      "kind": "ssh",
      "status": "ok",        // ok | error
      "output": {
        "stdout": "實際輸出",
        "stderr": ""
      }
    }
  ]
}
```

- `status: "done"` + `steps[].status: "ok"` → 全部成功
- `status: "failed"` → 有步驟失敗，看 `steps[].error`
- exit code 3 = 執行失敗，看 `jobs/failed/`

---

## 故障排查

```bash
# gateway 是否開著？
agent-switch status

# 命令被擋？
tail -20 /Users/agentbot/logs/agent-ssh.log

# runner 層錯誤？
tail -20 /Users/ryan/meta-agent/tools/agent-ssh-gateway/logs/runner.log

# job 卡在 running？
ls /Users/ryan/meta-agent/tools/agent-ssh-gateway/jobs/running/
# → 手動 mv jobs/running/<id>.json jobs/incoming/<id>.json
```

---

## Output Contract

執行完畢後必須輸出：
1. job_id
2. status（done / failed）
3. 每個 step 的 stdout 摘要
4. 若 failed：error 原因 + 下一步建議

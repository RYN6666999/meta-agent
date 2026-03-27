# AI Agent SSH Gateway — 介面規格（SPEC）

> 此文件為各層介面的單一真理源。每次新增功能前先更新此文件，確保介面定義不因堆疊而漂移。

---

## 文件治理規則

**定位：Runtime Contract**
本文件只記錄「目前程式碼已實作且可被依賴」的介面。

| 規則 | 說明 |
|------|------|
| ✅ 可寫入 | 已實作、已驗收、AI 可直接依據呼叫的介面 |
| ❌ 不可寫入 | 尚未實作的草稿、計劃中的欄位、未決定的設計意圖 |
| 📄 草稿去處 | 未實作內容請寫入 `FUTURE.md` |

**Phase 開工流程：**
1. 在 `FUTURE.md` 收斂該 phase 介面草稿
2. 決定落地介面後，寫進本文件
3. 實作完成後同步更新 `README.md` / `DELTA.md`

**判準：** 如果 Claude 今天照這段文字寫 code，是否安全？
→ 會 → 放這裡　→ 不會（尚未實作） → 放 `FUTURE.md`

---

## 目錄

1. [架構總覽](#1-架構總覽)
2. [Job 格式規格](#2-job-格式規格)
3. [Step 類型規格](#3-step-類型規格)
4. [設定檔規格](#4-設定檔規格)
5. [模組介面規格](#5-模組介面規格)
6. [Auth State 規格](#6-auth-state-規格)
7. [檔案系統規格](#7-檔案系統規格)
8. [SSH Gateway 規格](#8-ssh-gateway-規格)
9. [Exit Code 規格](#9-exit-code-規格)
10. [環境變數規格](#10-環境變數規格)

---

## 1. 架構總覽

```
Agent / Caller
    │
    ▼
run-job.ts          ← Job Runner（進入點）
    ├── playwright-worker.ts  ← Web 步驟執行器
    │       └── auth/sites/<site>/auth-state.json
    ├── ssh-worker.ts         ← SSH 命令執行器
    │       └── agent-gateway.sh（目標主機）
    └── config.ts             ← 設定載入器
            └── runner.config.json
```

---

## 2. Job 格式規格

### 2.1 Schema

```typescript
interface Job {
  job_id: string;           // 唯一識別符，建議格式：<type>-<YYYYMMDD>-<seq>
  type:   "web" | "ssh" | "hybrid";
  steps:  Step[];           // 依序執行，任一失敗即中止
}
```

### 2.2 命名慣例

| 欄位 | 格式 | 範例 |
|------|------|------|
| `job_id` | `<type>-<date>-<seq>` | `hybrid-20260326-001` |
| 檔名 | `<job_id>.json` | `hybrid-20260326-001.json` |

### 2.3 完整範例

```json
{
  "job_id": "hybrid-20260326-001",
  "type": "hybrid",
  "steps": [
    { "kind": "web",  "site": "fundodo", "action": "open_page", "url": "https://fundodo.net/fundodo/" },
    { "kind": "web",  "site": "fundodo", "action": "get_text",  "selector": "h1" },
    { "kind": "ssh",  "command": "date" }
  ]
}
```

---

## 3. Step 類型規格

### 3.1 WebStep

```typescript
interface WebStep {
  kind:      "web";
  site:      string;     // 對應 runner.config.json sites 的 key
  action:    WebAction;
  url?:      string;     // open_page 必填
  selector?: string;     // click / fill / get_text / wait_for 必填
  value?:    string;     // fill 必填
}

type WebAction =
  | "open_page"     // 導覽到 URL（偵測 AUTH_EXPIRED）
  | "click"         // 點擊元素
  | "fill"          // 填入文字
  | "get_text"      // 取得元素文字內容
  | "wait_for"      // 等待元素出現（最長 15s）
```

| action | url | selector | value |
|--------|-----|----------|-------|
| `open_page` | ✅ 必填 | — | — |
| `click` | — | ✅ 必填 | — |
| `fill` | — | ✅ 必填 | ✅ 必填 |
| `get_text` | — | ✅ 必填 | — |
| `wait_for` | — | ✅ 必填 | — |

### 3.2 SshStep

```typescript
interface SshStep {
  kind:    "ssh";
  command: string;   // 單次命令，由 agent-gateway.sh 黑名單過濾
}
```

---

## 4. 設定檔規格

路徑：`runner/runner.config.json`

```typescript
interface RunnerConfig {
  ssh: {
    host:                  string;                          // SSH 目標主機 IP 或 hostname
    user:                  string;                          // SSH 使用者（預設 agentbot）
    keyPath:               string;                          // 私鑰路徑（支援 ~ 展開）
    port:                  number;                          // 預設 22
    strictHostKeyChecking: "yes" | "no" | "accept-new";    // 生產環境用 accept-new
    connectTimeoutSec:     number;                          // 連線逾時（秒）
  };
  sites: {
    [siteName: string]: {
      loginUrl: string;    // 對應 refresh-auth 的登入頁
    };
  };
  runner: {
    jobTimeoutMs: number;  // 整個 job 的最長執行時間（ms）
  };
}
```

**env var 覆寫（SSH 設定）：**

| env var | 覆寫欄位 |
|---------|---------|
| `SSH_HOST` | `ssh.host` |
| `SSH_USER` | `ssh.user` |
| `SSH_KEY_PATH` | `ssh.keyPath` |

---

## 5. 模組介面規格

### 5.1 `config.ts`

```typescript
loadConfig(): RunnerConfig
getSshConfig(): SshConfig          // 合併 env var 覆寫
getSiteLoginUrl(site: string): string | undefined
expandHome(p: string): string
```

### 5.2 `playwright-worker.ts`

```typescript
class WorkerSession {
  constructor(site: string)
  init(): Promise<void>             // 載入 auth state，建立 context
  openPage(url: string): Promise<StepResult>
  checkAuthenticated(): Promise<boolean>
  runStep(action: Record<string, unknown>): Promise<StepResult>
  close(): Promise<void>
}

type StepResult =
  | { status: "ok";           output: unknown }
  | { status: "AUTH_EXPIRED"; output: null }
  | { status: "error";        output: null; message: string }
```

### 5.3 `ssh-worker.ts`

```typescript
runSshCommand(command: string): Promise<SshCommandResult>

interface SshCommandResult {
  stdout:   string;
  stderr:   string;
  exitCode: number;
  error?:   string;   // spawn 失敗時填入
}
```

### 5.4 `refresh-auth.ts`（CLI）

```bash
SITE=<name> npm run refresh-auth
# LOGIN_URL 可選，未提供時從 runner.config.json sites.<name>.loginUrl 查詢
```

### 5.5 `run-job.ts`（CLI）

```bash
npm run run-job -- <job-file.json>
```

---

## 6. Auth State 規格

```
auth/
  sites/
    <site>/
      auth-state.json    # Playwright storageState（cookies + localStorage）
      profile/           # launchPersistentContext user data（完整 browser state）
```

- `auth-state.json`：Playwright `BrowserContext.storageState()` 輸出格式
- `profile/`：launchPersistentContext 用，數百 MB，不入版本庫
- 整個 `auth/sites/` 由 `.gitignore` 排除

---

## 7. 檔案系統規格

### 7.1 Job 目錄

```
jobs/
  incoming/    # 等待執行的 job（放入即排隊）
  running/     # 執行中（runner 自動移入，不要手動放置）
  done/        # 完成：<id>.json + <id>.result.json
  failed/      # 失敗：<id>.json + <id>.result.json
  examples/    # 範本（可提交版本庫）
```

### 7.2 Result 格式

```typescript
interface JobResult {
  job_id:      string;
  status:      "done" | "failed" | "auth_expired";
  started_at:  string;   // ISO 8601
  finished_at: string;   // ISO 8601
  steps: Array<{
    kind:     "web" | "ssh";
    status:   "ok" | "error" | "AUTH_EXPIRED";
    output?:  unknown;
    error?:   string;
  }>;
  error?: string;        // job 層級錯誤訊息
}
```

---

## 8. SSH Gateway 規格

### 8.1 agent-gateway.sh

| 項目 | 規格 |
|------|------|
| 觸發方式 | sshd ForceCommand |
| 命令來源 | `$SSH_ORIGINAL_COMMAND` |
| 開關檢查 | `/Users/agentbot/.ssh/enabled.flag` 存在才允許 |
| 過濾方式 | 黑名單 regex（非白名單） |
| 工作目錄 | `/Users/agentbot/workspace` |
| 執行方式 | `bash -lc "<command>"` |
| Log 路徑 | `/Users/agentbot/logs/agent-ssh.log` |
| Log 格式 | `<ISO8601> \| ALLOW/DENY/DONE  \| cmd=... [exit=N] [reason=...]` |

### 8.2 黑名單（關鍵項目）

`sudo` / `su` / `rm -rf` / `reboot` / `shutdown` / `mkfs` / `dd if=` / `nc` / `ncat` / `socat` / `ssh` / `scp` / `curl|sh` / `wget|sh` / 寫入 `/etc` `/boot`

### 8.3 agent-switch

| 命令 | 行為 |
|------|------|
| `agent-switch on` | 建立 enabled.flag + 還原 authorized_keys |
| `agent-switch off` | 刪除 enabled.flag + 停用 authorized_keys |
| `agent-switch status` | 顯示 flag / authorized_keys / 整體狀態 |

---

## 9. Exit Code 規格

### run-job.ts

| Code | 意義 |
|------|------|
| 0 | Job 完成（done） |
| 1 | 參數錯誤（缺少 job 檔案） |
| 2 | Job JSON 格式錯誤 |
| 3 | Job 執行失敗（failed） |
| 4 | AUTH_EXPIRED |

### agent-gateway.sh

| Code | 意義 |
|------|------|
| 0 | 命令執行成功 |
| 1 | 命令被拒絕 / 開關關閉 / 空命令 |
| N | 被執行命令的原始 exit code |

### refresh-auth.ts

| Code | 意義 |
|------|------|
| 0 | auth state 儲存成功 |
| 1 | 缺少必要環境變數 |
| 2 | storageState 儲存失敗 |

---

## 10. 環境變數規格

| 變數 | 用途 | 預設值 | 覆寫對象 |
|------|------|--------|----------|
| `SSH_HOST` | SSH 目標主機 | `runner.config.json` | `ssh.host` |
| `SSH_USER` | SSH 使用者 | `agentbot` | `ssh.user` |
| `SSH_KEY_PATH` | SSH 私鑰路徑 | `~/.ssh/agentbot_ed25519` | `ssh.keyPath` |
| `SSH_PORT` | SSH 連接埠 | `22` | — |
| `SITE` | refresh-auth 網站名稱 | — | 必填 |
| `LOGIN_URL` | refresh-auth 登入頁 | `config.sites[SITE].loginUrl` | 可選 |
| `BROWSER` | Playwright 引擎 | `chromium` | — |

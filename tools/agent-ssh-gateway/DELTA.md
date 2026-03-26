# 計劃 vs 實際落地 — 差異紀錄（P0–P3）

> 給原計劃制定者的現況說明。
> 紀錄「原計劃寫了什麼」vs「實際做了什麼」，以及每個決策的理由。

---

## 總覽

| | 原計劃 | 實際落地 |
|--|--------|----------|
| 目標平台 | Linux | **macOS M2**（個人機） |
| Phase 順序 | Playwright → Job Runner → SSH | **SSH 優先** → Playwright → Job Runner |
| Auth 模型 | 單一 auth-state.json | **多 profile**（per-site 獨立目錄） |
| Job 格式 | `{id, type, target, actions[]}` | **`{job_id, type, steps[{kind,...}]}`** |
| 設定方式 | 環境變數 | **runner.config.json** + env var 覆寫 |
| 命令過濾 | 白名單（只允許列出的命令） | **黑名單**（阻擋危險命令，其餘放行） |
| 生產強化 | Phase 5 才做 | **Phase 3 一併完成** |

---

## Phase 0 — 專案骨架

**差異：無**。目錄結構、.gitignore、TypeScript 設定與原計劃一致。驗證腳本 19/19 全過。

---

## Phase 1 — 原計劃：Playwright auth state／實際：SSH Gateway

### 順序對調原因

原計劃 Phase 1 是 Playwright，Phase 3 才做 SSH。
實際執行時先做 SSH Gateway，理由：

- SSH Gateway 是最底層的安全邊界，後面所有 Phase 都依賴它
- Playwright 的 auth 機制可獨立測試，不需 SSH 就能驗
- 先確認「AI agent 能不能安全執行 shell 命令」比「能不能操作網頁」更關鍵

### 與原計劃的具體差異

**平台從 Linux → macOS M2**

原計劃假設部署到 Linux 主機，實際部署到開發機（macOS M2）。需要的調整：

| 項目 | Linux（原計劃） | macOS（實際） |
|------|----------------|--------------|
| 使用者 home | `/home/agentbot` | `/Users/agentbot` |
| 建立使用者 | `useradd` | `dscl . -create` |
| sshd 重啟 | `systemctl reload sshd` | `launchctl kickstart -k system/com.openssh.sshd` |
| SSH 允許群組 | 不需要 | `dseditgroup -o edit -a agentbot -t user com.apple.access_ssh` |
| sshd_config.d | 預設存在 | 需手動建立，但 Include 指令已在預設 config |

**命令過濾：白名單 → 黑名單**

原計劃 stub 是白名單設計（只有列出的命令才允許）。
實際改為黑名單，理由：原型階段 agent 需要執行的命令無法事先全部列出（`ls`、`cat`、`echo`、`date`、`grep`⋯ 太多）。黑名單阻擋破壞性命令，其餘放行，降低開發摩擦。

> ⚠️ 生產環境若要升級為白名單，修改 `agent-gateway.sh` 的過濾邏輯即可，介面不變。

**`sshd_config.agentbot.conf` 補強**

原計劃 stub 沒有 `ForceCommand`。實際新增：

```
ForceCommand /usr/local/bin/agent-gateway.sh
AllowStreamLocalForwarding no
GatewayPorts no
AllowAgentForwarding no
PermitTunnel no
```

---

## Phase 2 — 原計劃：Playwright auth state（同名，但實作有差異）

### 最大差異：單 auth → 多 profile

原計劃設計為單一 `auth/auth-state.json`，對應一個網站、一個帳號。

實際需求確認後，agent 需要操作多個網站（fundodo、GitHub、Cloudflare、Genspark、Google），因此改為 per-site 獨立目錄：

```
# 原計劃
auth/
  auth-state.json

# 實際落地
auth/
  sites/
    fundodo/
      auth-state.json
      profile/
    github/
      auth-state.json
      profile/
```

`refresh-auth.ts` 改為必須指定 `SITE=<name>`，並在 Phase 3 進一步整合到 `runner.config.json`（不需要再記各網站的 loginUrl）。

### `refresh-auth.ts` 使用方式對比

```bash
# 原計劃
LOGIN_URL=https://example.com/login npm run refresh-auth

# 實際（Phase 2）
SITE=github LOGIN_URL=https://github.com/login npm run refresh-auth

# 實際（Phase 3 之後，config 整合後）
SITE=github npm run refresh-auth    # URL 自動從 runner.config.json 查詢
```

---

## Phase 3 — 原計劃：Job Runner（web job）／實際：Hybrid Job Runner + 生產強化

### Job 格式大改版

原計劃的 Job 格式：

```json
{
  "id": "job-001",
  "type": "web",
  "target": "https://example.com",
  "actions": [
    { "type": "goto", "url": "..." }
  ]
}
```

實際落地的 Job 格式：

```json
{
  "job_id": "hybrid-001",
  "type": "hybrid",
  "steps": [
    { "kind": "web", "site": "fundodo", "action": "open_page", "url": "..." },
    { "kind": "ssh", "command": "date" }
  ]
}
```

**差異點：**

| 欄位 | 原計劃 | 實際 | 理由 |
|------|--------|------|------|
| 識別符 | `id` | `job_id` | 避免與保留字衝突，語義更明確 |
| 步驟欄位 | `actions` | `steps` | 支援 web + ssh 混合，`actions` 語義太窄 |
| 步驟識別 | `type` | `kind` | `type` 在 job 層已使用，`kind` 區分層級 |
| 網站指定 | job 層的 `site` | step 層的 `site` | hybrid job 中不同 step 可用不同網站 |
| job 類型 | `web` / `ssh` | `web` / `ssh` / **`hybrid`** | 新增 hybrid，支援混合執行 |

### 原計劃 Phase 4 提前合併

原計劃：
- Phase 3 做 web job
- Phase 4 才做 SSH job 整合

實際：Phase 3 直接做 hybrid，web + ssh 一次整合。原因：兩者在 `run-job.ts` 的整合點一樣，分開做反而多一次重構。Phase 4 的獨立任務消失，由 Phase 3 吸收。

### 生產強化提前（原計劃 Phase 5）

以下原計劃放到 Phase 5 的項目，在 Phase 3 一併完成：

| 項目 | 原計劃時機 | 實際時機 | 說明 |
|------|-----------|---------|------|
| SSH `StrictHostKeyChecking` | Phase 5 | Phase 3 | 改為 `accept-new`（防 MITM） |
| Job 逾時保護 | Phase 5 | Phase 3 | `Promise.race` + 可設定 `jobTimeoutMs` |
| 中央設定檔 | 未計劃 | Phase 3 | `runner.config.json` |
| Result 與 Job 定義分離 | 未計劃 | Phase 3 | `<id>.json` + `<id>.result.json` |

---

## 新增項目（原計劃未提及）

### `runner/runner.config.json`

原計劃所有設定靠環境變數。實際加入中央設定檔，整合：
- SSH target（host / user / keyPath / port）
- 各網站 loginUrl
- job 逾時

### `runner/src/config.ts`

設定載入器模組，提供型別安全的 config 存取。原計劃無此模組。

### `SPEC.md`

完整的介面規格文件。原計劃無。涵蓋 Job schema、Step 介面、Config 型別、模組 API、Auth 路徑、Exit code、env var。

---

## 原計劃 Phase 4、5 現況

| 原計劃 Phase | 現況 |
|-------------|------|
| Phase 4：Runner 整合 SSH job | **已完成**（併入 Phase 3） |
| Phase 5：Log 規範與錯誤處理 | **未開始**，但生產強化部分已提前完成 |

Phase 5 剩餘待完成項目：
- Log rotation（`agent-ssh.log` 無上限）
- Runner 層的結構化 log（目前只有 console.log）
- AUTH_EXPIRED 自動重試流程

---

## 當前目錄結構（實際）

```
agent-ssh-gateway/
  auth/
    sites/                    ← 不入庫（.gitignore）
      fundodo/
        auth-state.json
        profile/
  host/
    bin/
      agent-gateway.sh        ← 黑名單過濾，部署至 /usr/local/bin/
      agent-switch            ← on/off/status 開關，部署至 /usr/local/bin/
    ssh/
      sshd_config.agentbot.conf  ← 部署至 /etc/ssh/sshd_config.d/
  jobs/
    incoming/                 ← 放 job JSON 即觸發執行
    running/                  ← runner 自動管理
    done/                     ← <id>.json + <id>.result.json
    failed/                   ← <id>.json + <id>.result.json
    examples/                 ← 範本（入庫）
  runner/
    runner.config.json        ← SSH + sites + timeout 設定
    src/
      config.ts               ← 設定載入器（新增）
      run-job.ts              ← Job Runner 主程式（大改版）
      refresh-auth.ts         ← 手動登入存 auth state
      playwright-worker.ts    ← WorkerSession（web 步驟執行）
      ssh-worker.ts           ← runSshCommand（ssh 步驟執行）
  scripts/
    verify-structure.sh
  SPEC.md                     ← 介面規格（新增）
  DELTA.md                    ← 本文件（新增）
  README.md
```

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

**命令過濾：白名單 → 黑名單 → P7 分級治理**

原計劃 stub 是白名單設計（只有列出的命令才允許）。
Phase 1 實際改為黑名單，理由：原型階段 agent 需要執行的命令無法事先全部列出（`ls`、`cat`、`echo`、`date`、`grep`⋯ 太多）。黑名單阻擋破壞性命令，其餘放行，降低開發摩擦。

Phase 7 升級為分級治理（詳見後文 Phase 7 章節），不是直接切換白名單，
而是引入 `audit / enforce / legacy-blacklist / break-glass` 四種模式。

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

## Phase 6 — n8n 整合（P6-MVP）

### 方案選型

三種方案評估後決策：

| 方案 | 決策 |
|------|------|
| A. Execute Command（同步） | **原始計劃，最終改以 Code node 實現** |
| B. Poll loop + watcher daemon | 不做 |
| C. Callback URL（push） | 保留為 P6.5 候選 |

### 實際落地：Code node 模式（非 Execute Command）

原計劃使用 n8n Execute Command node，但此版本 n8n（2.36.1 / n8n-with-ffmpeg）不支援該 node type。改用 **Code node + Node.js `child_process`**，行為等效：

```
Code node
  → fs.writeFileSync  (寫 jobs/incoming/<id>.json)
  → execSync npm run run-job  (執行 runner)
  → fs.readFileSync  (讀 jobs/done/<id>.result.json)
```

### Docker 執行邊界（P6 發現的根本問題）

n8n 跑在 Docker 容器內，`127.0.0.1` 指向容器自身，不是 host。

| 項目 | 問題 | 解法 |
|------|------|------|
| 容器讀不到 host 的 jobs/ | 無 volume mount | 掛入 `/workspace/agent-ssh-gateway` |
| 容器讀不到 SSH key | 無 volume mount | 掛入 `/home/node/.ssh/agentbot_ed25519:ro` |
| 容器 SSH 連不到 host | `127.0.0.1` = 容器自身 | 改用 `host.docker.internal` |
| readWriteFile 被拒絕 | `N8N_RESTRICT_FILE_ACCESS_TO` 白名單未包含新路徑 | 同步更新 env var |
| Code node 無法用 `process.env` | n8n sandbox 不提供 `process` 物件 | 硬寫必要 env 變數 |

### 新增 / 修改項目

| 項目 | 說明 |
|------|------|
| `scripts/run-job-n8n.sh` | host 端薄包裝（供直接 shell 呼叫用，n8n workflow 未使用） |
| `jobs/examples/n8n-trigger-job.json` | n8n workflow 用的 SSH job 範本 |
| `Projects/n8n/docker-compose.yml` | 新增 2 個 volume mount + 更新 `N8N_RESTRICT_FILE_ACCESS_TO` |
| `README.md` Phase 6 章節 | 記錄實際落地的 Code node 方式與 Docker 設定 |

### 未改動項目

- `run-job.ts`：無修改，CLI 介面完全不變
- Job schema：無新增欄位
- `runner.config.json`：無修改

### FUTURE.md 更新

- P6 標記為 `Promoted`（Code node 模式）
- 新增 **P6.5** 候選：`callback_url` + webhook push 升級條件

---

## 原計劃 Phase 4、5 現況

| 原計劃 Phase | 現況 |
|-------------|------|
| Phase 4：Runner 整合 SSH job | **已完成**（併入 Phase 3） |
| Phase 5：Log 規範與錯誤處理 | **已完成** |

Phase 5 完成項目：
- Log rotation（`agent-gateway.sh` `rotate_log()`，超過 512KB 自動輪轉，保留 3 份）→ P5.2
- Runner 結構化 log（`run-job.ts` `rlog()`，JSON Lines 寫入 `logs/runner.log`）→ P5.1
- AUTH_EXPIRED retry hint（偵測後輸出明確指引 + exit code 4）→ P5.3

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

---

## Phase 7 — P7 分級風控升級（Controlled Allowlist Mode）

### 與原 Phase 1 黑名單的差異

| 項目 | Phase 1（黑名單） | Phase 7（分級治理） |
|------|-----------------|-------------------|
| 過濾邏輯 | BLACKLIST array，命中擋、未命中放 | HARD_DENY + ALLOWLIST + OBSERVELIST 三層 |
| 模式 | 單一（黑名單） | 四種（legacy / audit / enforce / break-glass） |
| 未知命令 | 放行，無記錄 | audit：放行+記錄；enforce：拒絕 |
| 設定方式 | 寫死在 agent-gateway.sh | 外部化至 gateway-policy.sh，可熱修改 |
| 模式切換 | 無 | `agent-switch mode <mode>` |
| Log 格式 | `LEVEL \| cmd=... exit=...` | 新增 `mode= decision= category= reason=` |
| 緊急回退 | 無（只有 off） | `legacy-blacklist` mode 或 `agent-switch off` |

### 為什麼不直接切白名單

直接切成 `enforce` 的風險：
- 真實工作現場命令面未完整盤點
- 過嚴的風控會立即絆腳 n8n / runner 流程
- 沒有觀察期，allowlist 必然不完整

P7 的解法是 **audit-first**：先觀察再收斂，不在命令面不明的情況下直接 enforce。

### gateway-policy.sh 的引入目的

- 把規則從主腳本分離，讓調整規則不需改 agent-gateway.sh
- 模式切換只改 `GATEWAY_MODE=` 那一行
- 未來可以做 per-site 或 per-job-type 的不同 policy（在此版本先不實作）

### P7 新增的 Log 欄位

```
mode=audit decision=allow category=allowlist cmd=echo hello reason=in allowlist
```

| 欄位 | 說明 |
|------|------|
| `mode` | 目前 GATEWAY_MODE |
| `decision` | allow / deny |
| `category` | allowlist / hard-deny / observe / unknown / legacy / break-glass |
| `reason` | 決策原因 |

### P7 驗收結果（2026-03-27）

8 個驗收 case 全過（真實 SSH 路徑）：

| Case | 命令 | Mode | 預期 | 結果 |
|------|------|------|------|------|
| 1 | `echo hello` | audit | allow/allowlist | ✅ |
| 2 | `jq --version` | audit | allow/observe | ✅ |
| 3 | `htop` | audit | allow/unknown | ✅ |
| 4 | `htop` | enforce | deny/unknown | ✅ |
| 5 | `sudo ls` | audit | deny/hard-deny | ✅ |
| 5b | `sudo ls` | enforce | deny/hard-deny | ✅ |
| 5c | `sudo ls` | break-glass | deny/hard-deny | ✅ |
| 6 | `htop` | break-glass | allow/break-glass | ✅ |

P6 回歸：`echo / date / ls / npm` 全在 allowlist，P6 job 流程不受影響。

### P7.1 觀察期結果（2026-03-27）

跑 4 輪真實 job（ssh-only x2 / n8n trigger x1 / hybrid x1），發現並修正一個 hard-deny 誤觸：

**`rm -rf /workspace/...` 被舊 rm pattern 誤擋**
- 原因：Phase 1 繼承的 rm pattern 過寬，`rm -rf <任意含/路徑>` 都擋
- 修正：改為只擋根目錄 `/` 和系統路徑（/etc /boot /System /usr /private /bin /sbin /var/root）
- 結果：workspace 下 `rm -rf` 正常通行，系統路徑仍擋

**P7.1 decision 統計（觀察期）**：

| category | 次數 | 備註 |
|----------|----:|------|
| allowlist | 25 | 所有真實 job 命令 |
| hard-deny | 11 | 包含 2 次誤觸（已修正） |
| unknown | 2 | `htop`（人工測試，非 job 依賴） |
| observe | 1 | `jq`（驗證測試） |

結論：真實 job 命令面已全覆蓋，allowlist 穩定，可評估 P7.2 enforce 上線。

### P7.2 Rollback 演練與 enforce 正式上線（2026-03-27）

**Rollback 演練 A**（enforce → audit，8 秒）：
- enforce 下 `fortune`（unknown）被擋
- `agent-switch mode audit` → 立即恢復通行
- log 可清楚區分 enforce deny vs audit allow

**Rollback 演練 B**（enforce → legacy-blacklist）：
- `agent-switch mode legacy-blacklist` → 正常 job 跑通
- hard-deny（sudo）在 legacy-blacklist 仍擋住

**enforce 正式切換**：
- ssh-only job（echo / date / ls / mkdir / rm -rf /workspace/...）: ✅ DONE
- n8n-style job: ✅ DONE
- hard-deny: ✅

**發現的新事實：agent-switch status 在非 agentbot 身份下誤報**
- `/Users/agentbot/.ssh/` 是 `drwx------`，ryan 無法讀取
- gateway 以 agentbot 身份透過 ForceCommand 執行，能正確看到 `enabled.flag`
- `agent-switch status` 已更新顯示為 `UNKNOWN`（非 OFF），避免混淆
- 功能正確，僅 UX 問題

---

## Phase 8 — AUTH_EXPIRED 通知與 Re-queue（P5.3 升級）

### 方案決策：B（n8n 通知 + 人工補登）

否決方案 A（headful browser）的理由：
- runner 跑在 SSH session，`headless: false` 需要 DISPLAY，環境不穩定
- 2FA/CAPTCHA 自動化邊界不明，最終仍需人工介入
- 自動重登有觸發風控鎖帳的風險

### P8 runner 端落地（2026-03-27）✅

**`config.ts`** — 新增 `AuthNotifyConfig` + `getAuthNotifyConfig()`

**`run-job.ts`** — 新增 `notifyAuthExpired(jobId, site, filename)`：
- 偵測 `auth_expired` 時 best-effort POST 到 n8n webhook
- 5s timeout，失敗只記 WARN，不影響 exit code 或 job 狀態
- Payload：`{ event, job_id, site, job_file, login_url, failed_at }`
- console.error 提示已更新為包含 re-queue 指令

**`runner.config.json`** — 新增 `authNotify.webhookUrl`（已啟用）：
```json
"authNotify": {
  "webhookUrl": "http://localhost:5678/webhook/auth-expired",
  "timeoutMs": 5000
}
```

| 項目 | 說明 |
|------|------|
| 回滾方式 | 移除 `authNotify` key 即退回舊行為 |
| 向後相容 | `authNotify` 未設定時靜默跳過，無副作用 |

### P8.1 n8n Workflow 落地（2026-03-27）✅

**Workflow ID**: `SHhtbahAm28jNVVJ`
**名稱**: SSH Gateway — AUTH_EXPIRED 通知 (P8.1)
**狀態**: active = true
**Webhook URL**: `http://localhost:5678/webhook/auth-expired`

**架構（最終版，已換用原生 Telegram node）**：
```
POST /webhook/auth-expired (onReceived 立即回應 200)
  ↓
Code node: 格式化 HTML 訊息（site / job_id / login_url / 補救步驟）
  ↓
n8n Telegram node（原生，credential: "Agent SSH Gateway Bot"）
  → chatId: 1469326872
  → parse_mode: HTML
```

**原始設計（已廢棄）**: Code node 自寫 https.request → LINE Notify
- LINE Notify 已於 2025-03-31 停服，改用 Telegram
- 自寫 HTTP code 改為 n8n 原生 Telegram node（更穩定，有重試）

**Telegram 設定（已完成）**：

| 項目 | 值 |
|------|-----|
| Bot 名稱 | Qwekdbjsjw_bot |
| Bot Token | 存於 `.secrets.json`（gitignored） |
| Chat ID | 1469326872（Ryan @RYN1491） |
| n8n Credential | "Agent SSH Gateway Bot"（id: t5ML2WeYvrnTvenU, type: telegramApi） |

**E2E 驗收（2026-03-27）**：

| 項目 | 結果 |
|------|------|
| webhook 接收 payload | ✅ |
| runner → webhook 鏈路 | ✅ |
| 原生 Telegram node 發送 | ✅ 收到 HTML 格式通知 |
| 非阻塞（webhook 失敗） | ✅ best-effort，不影響 job exit code |

### P8.2 TG 指令頻道（2026-03-27）✅

**目標**: 雙向通道，可從 Telegram 下達指令

**廢棄方案**: n8n Telegram Trigger（需 HTTPS webhook，本地 n8n 無法啟用）

**落地方案**: `agent-tg-daemon.sh` bash polling daemon（getUpdates long-poll）

#### 架構

```
Telegram Server
  ↑↓ getUpdates long-poll (timeout=30s)
agent-tg-daemon.sh（常駐於 host，launchd）
  ↓ 安全過濾：chat_id != AUTHORIZED → 靜默丟棄
  ↓ 指令解析：只接受 /status /jobs /requeue /help
  ↓ 讀取 gateway-policy.sh（唯讀，取 GATEWAY_MODE）
  ↓ 結構化執行（無任意 shell）
  ↓ sendMessage 回覆 HTML 格式
```

#### 支援指令

| 指令 | 功能 |
|------|------|
| `/status` | Gateway 狀態、GATEWAY_MODE、jobs 計數 |
| `/jobs` | 列出 failed/ 中的 job ID + 失敗時間 |
| `/requeue <job_id>` | 顯示 re-queue 指令（不自動執行，需人工確認） |
| `/help` | 列出所有指令 |

#### 安全設計

| 項目 | 措施 |
|------|------|
| 未授權來源 | chat_id 白名單（1469326872），其餘靜默丟棄並 log |
| 指令隔離 | 只接受結構化指令，不執行任意 shell |
| job_id 注入防護 | regex 驗證 `^[a-zA-Z0-9_-]+$` |
| /requeue 審核 | 顯示 cp 指令，不自動執行 |
| gateway-policy.sh | 唯讀 grep，不 source |

#### 部署檔案

| 檔案 | 路徑 |
|------|------|
| daemon 腳本 | `host/bin/agent-tg-daemon.sh` → `/usr/local/bin/agent-tg-daemon.sh` |
| launchd plist | `host/launchd/com.agentbot.tg-daemon.plist` → `~/Library/LaunchAgents/` |
| log | `logs/tg-daemon.log`（結構化，含 timestamp + level） |

#### 部署指令（一次性）

```bash
# 1. 複製腳本
sudo cp host/bin/agent-tg-daemon.sh /usr/local/bin/
sudo chmod 755 /usr/local/bin/agent-tg-daemon.sh

# 2. 載入 launchd
cp host/launchd/com.agentbot.tg-daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.agentbot.tg-daemon.plist
launchctl start com.agentbot.tg-daemon

# 3. 確認
launchctl list | grep tg-daemon
tail -f logs/tg-daemon.log
```

#### 設定來源

Bot token 從 `.secrets.json` 自動讀取（`telegram.botToken`），或設 `TG_BOT_TOKEN` env var 覆寫（launchd plist 中預留 EnvironmentVariables 區塊，預設以 `.secrets.json` 讀取）。

### 未改動項目

- `gateway-policy.sh` / `agent-gateway.sh` / `agent-switch`：無修改
- Job schema（Job / WebStep / SshStep）：無修改
- P7 的所有封版內容：無修改

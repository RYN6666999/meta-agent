# AI Agent SSH Gateway — 未來設計意圖（FUTURE）

> **定位：Design Intent / Draft Contract（non-normative）**
> 本文件記錄尚未實作的介面草稿、決策理由、替代方案與未解問題。
> **不能被當成執行依據。不要依據此文件呼叫或實作任何 API。**

---

## 文件狀態說明

每個 Phase 有三種狀態：

| 狀態 | 意義 |
|------|------|
| `Draft` | 設計意圖，介面尚未定案 |
| `Decided` | 介面已定案，等待實作 |
| `Promoted` | 已移入 `SPEC.md`，可從本文件移除 |

---

## P6 — n8n Job Trigger 整合

**Status: Promoted**（已移入 README.md Phase 6 章節，核心介面以 **Code node + child_process** 模式落地）

---

## P6.5 — n8n Callback URL 升級（候選）

**Status: Draft**

### 目標
讓 runner 在 job 完成後主動 POST result 到指定 URL（n8n Webhook node），
不需 n8n 同步等待 CLI 結束。

### 預期資料流
```
n8n Write File → jobs/incoming/<id>.json（含 callback_url 欄位）
runner 執行完  → POST callback_url，body = JobResult
n8n Webhook    → 接收 result，繼續後續 workflow
```

### 可能新增 Job 欄位
```typescript
interface Job {
  // ...現有欄位不變
  callback_url?: string;   // 可選，未填則只寫 result 檔
}
```

### 升級條件（遇到以下任一再做）
- n8n workflow 常因長任務（>30s）卡住，阻塞 worker thread
- 需要 n8n 與 runner 完全解耦（不同機器）
- 需要非同步通知，不方便在 workflow 中同步等待

### 尚未決定
- callback failure 處理語義：失敗是否影響 job status（**建議：不影響，僅記 log**）
- timeout：callback HTTP request 最長等待（**建議：5s，best-effort**）
- URL 安全限制：只允許 http/https，禁止非法協定，限 localhost / 私網 allowlist
- retry policy：callback 失敗是否重送（**建議：不重送，避免複雜度**）

---

## P7 — 分級風控升級（Controlled Allowlist Mode）

**Status: Promoted**（已實作，P7.1 觀察期完成，P7.2 enforce 正式上線）

實作檔案：
- `host/bin/gateway-policy.sh`（新增）— 模式設定 + 三層規則
- `host/bin/agent-gateway.sh`（升級）— 四模式決策流 + 結構化 log
- `host/bin/agent-switch`（升級）— 新增 `mode` 子命令

驗收：8 case 全過（2026-03-27），P6 回歸無誤。
詳見 `DELTA.md` Phase 7 章節。

---

## P7.1 — audit 觀察期與 allowlist 收斂

**Status: Promoted**（已完成，2026-03-27）

### 觀察結果

| 類別 | 命令 | 出現次數 | 場景 | 結論 |
|------|------|------:|------|------|
| allowlist | echo, date, ls, mkdir, touch, cat, grep, rm, pwd | 25 | 真實 job | 穩定，不需調整 |
| unknown | htop | 2 | 人工測試 | keep unknown（非 job 依賴） |
| hard-deny 誤觸 | rm -rf /workspace/... | 2 | 舊 rm pattern 太寬 | **已修正** |

### 修正紀錄

**rm hard-deny pattern 收斂（P7.1 主要產出）**

舊 pattern（Phase 1 遺留，過寬）：
```
rm[[:space:]]+-[^[:space:]]*r[^[:space:]]*[[:space:]].*/'
rm[[:space:]]+-rf[[:space:]]+
```

新 pattern（只擋根目錄與系統路徑）：
```
rm[[:space:]].*[[:space:]]+/([[:space:]]|$)
rm[[:space:]].*[[:space:]]+/(etc|boot|System|usr|private|bin|sbin|var/root)(/|[[:space:]]|$)
```

**已驗證**：`rm -rf /Users/agentbot/workspace/...` 放行，`rm -rf /` / `/etc` / `/usr` 擋住。

### enforce 切換門檻
- [x] ssh-only job 通過（p71-ssh-obs-001, 002）
- [x] n8n trigger job 通過（p71-n8n-*）
- [x] hybrid job 通過（p71-hybrid-obs-001）
- [x] unknown 已趨穩（只有人工測試的 htop，真實 job 無 unknown）
- [ ] rollback 演練（仍建議在切 enforce 前執行一次）

---

## P7.2 — enforce 正式上線

**Status: Promoted**（已完成，2026-03-27）

### Rollback 演練結果

**Drill A：enforce → 誤擋 → 切回 audit**
- enforce 下 `fortune`（unknown）被擋：exit=1 ✅
- 切回 audit：`agent-switch mode audit`，8 秒內完成 ✅
- audit 下相同命令 gateway 放行（OS 找不到 binary 是 exit=127，不是 gateway 拒絕）✅

**Drill B：enforce → 誤擋 → 切回 legacy-blacklist**
- enforce 下 `fortune` 擋住 ✅
- 切回 `legacy-blacklist`：正常 job 跑通 ✅
- hard-deny（sudo）在 legacy-blacklist 仍擋住 ✅

**Drill B 補充：break-glass 確認非常態 rollback**
- break-glass 允許命令通過（包含記錄），但 hard-deny 照樣擋
- 定性為：救火用，不作為日常 fallback

### 正式切換結果（2026-03-27 14:24）

`GATEWAY_MODE` 已正式切換為 `enforce`。

驗收：
- ssh-only job（含 mkdir / touch / rm -rf workspace）: ✅ DONE
- n8n-style job（date / echo）: ✅ DONE
- hard-deny（sudo）: ✅ 擋住

### 已知事實：agent-switch status 顯示問題

`/Users/agentbot/.ssh/` 是 `drwx------`，非 agentbot 身份（如 ryan）無法讀取，
導致 `agent-switch status` 誤報 `UNKNOWN`。

實際狀態：
- `enabled.flag` 存在（root 所有，`-rw-------`）
- Gateway 以 agentbot 身份執行，`-f` 判斷能正確看到
- SSH 連線與 gateway 決策均正常運作

`agent-switch status` 已更新文字為 `UNKNOWN（以真實 SSH 測試確認）`，
避免誤導。待下次 sudo 部署時一併更新。

---

## P8 — AUTH_EXPIRED 通知與 Re-queue（P5.3 升級）

**Status: Decided**（方案 B 已定案，runner 端已實作，2026-03-27）

### 決策
採方案 B：**n8n 通知 → 人工補登 → re-queue**。

方案 A（headful browser 等待）否決理由：
- runner 跑在 SSH session，`headless: false` 需要 DISPLAY / Quartz，環境不穩定
- 2FA/CAPTCHA 自動化邊界不明，最終仍需人工介入 + 通知
- 自動重登有觸發風控鎖帳的風險
- 方案 B 是方案 A 的超集（通知 + 人工補登 ≥ headful 等待）

### 落地架構

```
auth_expired 發生
  ↓
run-job.ts notifyAuthExpired()
  → POST jobs/failed/<id>.json 路徑 + site + login_url 到 n8n webhook
  → best-effort（5s timeout，失敗只記 log，不影響 exit code）
  ↓
n8n webhook → 發 Slack / Line 通知
  訊息：site=xxx, job_id=xxx, login_url=xxx
  操作指引：
    1. SITE=xxx npm run refresh-auth
    2. cp jobs/failed/<id>.json jobs/incoming/<id>.json
  ↓
（選配）n8n 等待人工確認 → SSH step 自動 re-queue
```

### 實作檔案
- `runner/src/config.ts` — 新增 `AuthNotifyConfig` + `getAuthNotifyConfig()`
- `runner/src/run-job.ts` — 新增 `notifyAuthExpired()`，在 auth_expired 分支呼叫
- `runner/runner.config.json` — 新增 `_authNotify_DISABLED`（啟用時改 key 為 `authNotify`）

### 實作檔案
- `runner/src/config.ts` — 新增 `AuthNotifyConfig` + `getAuthNotifyConfig()`
- `runner/src/run-job.ts` — 新增 `notifyAuthExpired()`，在 auth_expired 分支呼叫
- `runner/runner.config.json` — `authNotify.webhookUrl = http://localhost:5678/webhook/auth-expired`

### n8n Workflow
- **ID**: `SHhtbahAm28jNVVJ`
- **名稱**: SSH Gateway — AUTH_EXPIRED 通知 (P8.1)
- **Webhook URL（啟動後）**: `http://localhost:5678/webhook/auth-expired`
- **測試 URL（未啟動）**: `http://localhost:5678/webhook-test/auth-expired`
- **通知方式**: Telegram Bot（`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`，直接寫在 Code node）
- **注意**: Line Notify 已於 2025-03-31 停服，改用 Telegram

### 驗收結果（2026-03-27）

| 項目 | 結果 |
|------|------|
| webhook 接收 payload | ✅ status=200，body 正確解析 |
| runner → webhook 鏈路 | ✅ runner log: `auth_notify sent status=200` |
| n8n execution 成功 | ✅ exec_id=173, status=success, mode=webhook |
| 真實 AUTH_EXPIRED 觸發 | ✅ fundodo session 過期，exit=4，payload 含正確 login_url |
| LINE_NOTIFY_TOKEN 缺少時 | ✅ 靜默回 `skipped: true`，不拋錯，exit code 不受影響 |
| 非阻塞（webhook 失敗） | ✅ best-effort，WARN log，不影響 job 主語義 |

**唯一待完成**：取得 Telegram Bot token + chat_id，填入 n8n workflow `Send Telegram Notify` 節點第 2-3 行：
```javascript
const TELEGRAM_BOT_TOKEN = 'YOUR_BOT_TOKEN';
const TELEGRAM_CHAT_ID   = 'YOUR_CHAT_ID';
```
取得步驟：
1. Telegram 搜尋 `@BotFather` → `/newbot` → 取得 `BOT_TOKEN`
2. 搜尋你的 bot，傳一則訊息
3. 開 `https://api.telegram.org/bot<TOKEN>/getUpdates` → 取 `result[0].message.chat.id`

### 尚未決定（留 P8.2）
- 人工確認後 n8n 自動 re-queue（HTTP callback 或 SSH step）
- site-specific 通知策略（重要 site 加急）
- 若 n8n 未啟動時 webhook 失敗的 fallback（目前: 靜默記 WARN）

---

## P9 — 多主機支援

**Status: Draft**

### 目標
讓 runner 可以對多台機器執行 SSH 命令，不限於單一 target。

### 預期 Config 變更

```typescript
// runner.config.json（草稿，非現行格式）
interface RunnerConfig {
  hosts: {
    [hostAlias: string]: {
      host:    string;
      user:    string;
      keyPath: string;
      port:    number;
    };
  };
  defaultHost: string;  // 未指定 host 時使用
  // ...現有其他欄位不變
}
```

### 預期 Step 變更

```typescript
// SshStep（草稿，非現行格式）
interface SshStep {
  kind:    "ssh";
  command: string;
  host?:   string;  // 對應 hosts 的 key，未指定則用 defaultHost
}
```

### 尚未決定
- 預設 host 選擇策略（defaultHost 或沿用現有 env var 覆寫）
- known_hosts 策略：每台主機獨立 known_hosts 還是共用
- SSH key mapping：一把 key 對多台，還是每台獨立 key
- `SSH_HOST` env var 的語義如何與 `hosts[]` 共存

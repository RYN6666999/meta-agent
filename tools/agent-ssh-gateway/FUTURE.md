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

**Status: Promoted**（已實作，audit 觀察期進行中）

實作檔案：
- `host/bin/gateway-policy.sh`（新增）— 模式設定 + 三層規則
- `host/bin/agent-gateway.sh`（升級）— 四模式決策流 + 結構化 log
- `host/bin/agent-switch`（升級）— 新增 `mode` 子命令

驗收：8 case 全過（2026-03-27），P6 回歸無誤。
詳見 `DELTA.md` Phase 7 章節。

---

## P7.1 — audit 觀察期與 allowlist 收斂

**Status: Draft**

### 目標
在 P7 `audit` 模式下收集真實命令面，建立 enforce 的切換門檻。

### 步驟
1. 部署 P7 至 agentbot，設定 `GATEWAY_MODE=audit`
2. 跑 N 輪真實 job（ssh-only / n8n trigger / hybrid）
3. 分析 `agent-ssh.log`：
   ```bash
   grep "category=unknown" /Users/agentbot/logs/agent-ssh.log | \
     grep -oP 'cmd=\S+' | sort | uniq -c | sort -rn
   ```
4. 將常見 unknown command 移入 `ALLOWLIST`
5. 將偶發或風險不明的保留在 `OBSERVELIST`
6. 觀察期結束條件：連續 10 輪 job 無新 unknown command

### enforce 切換門檻（待確認）
- [ ] ssh-only job 5 次無 unknown
- [ ] n8n trigger job 5 次無 unknown
- [ ] hybrid job 3 次無 unknown
- [ ] rollback 演練完成一次

---

## P7.2 — enforce 正式上線

**Status: Draft**（待 P7.1 完成後評估）

### 前置條件
- P7.1 觀察期完成
- allowlist 穩定（無新 unknown）
- rollback 流程文件化

### 切換方式
```bash
sudo agent-switch mode enforce
```

### 注意
enforce 上線後，新工具或新命令首次使用都會被拒。
建議保持 `legacy-blacklist` 為一鍵回退。

---

## P8 — AUTH_EXPIRED 自動重試（P5.3 升級）

**Status: Draft**

### 目標
目前 P5.3 偵測到 AUTH_EXPIRED 只輸出提示訊息（exit 4）。
P8 目標：真正無人值守，不需人工觸發 `refresh-auth`。

### 可能方案
- 方案 A：偵測到 AUTH_EXPIRED → 自動 launch headful browser → 等待人工登入 → 繼續 job
- 方案 B：偵測到 AUTH_EXPIRED → 透過 n8n 發通知（Slack / Line） → 人工補登後重新投 job

### 風險
- 網站風控可能偵測自動化重登並鎖帳號
- 2FA / CAPTCHA 無法自動完成，邊界在哪裡需要定義
- 人工補登界線：哪些 site 可以嘗試自動、哪些必須人工

### 尚未決定
- retry policy：失敗幾次後放棄？
- site-specific login hooks（不同網站的登入流程差異很大）
- job 重試語義：AUTH_EXPIRED 後，原 job 是否自動重新入隊

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

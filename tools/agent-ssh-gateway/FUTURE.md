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

**Status: Draft**

### 目標
讓 n8n workflow 可以觸發 job 並取得結果，把 SSH Gateway 接入主控腦自動化管線。

### 預期資料流
```
n8n workflow
  → drop job JSON 到 jobs/incoming/
  → poll jobs/done/<id>.result.json 或 jobs/failed/<id>.result.json
  → 取得 result 做後續判斷
```

### 可能新增介面
- trigger source 標記（result 裡記錄由誰觸發）
- callback URL / webhook（完成後主動通知 n8n）
- result polling 的等待策略

### 尚未決定
- push（webhook callback）vs poll（n8n 定時查 result）
- job 檔案落點是否改為 n8n 可直接存取的路徑
- 權限邊界：n8n process 是否有寫入 incoming/ 的權限

---

## P7 — 白名單升級（生產安全強化）

**Status: Draft**

### 目標
將 `agent-gateway.sh` 由黑名單模式升級為白名單模式。

### 前置作業
- 從 `agent-ssh.log` 取樣 agent 實際使用的命令集合
- 確認最小必要命令集（`echo`, `date`, `ls`, `cat`, `grep`, `pwd` 等）

### 相容策略（尚未決定）
- 方案 A：直接切換，prototype 期間黑名單已足夠
- 方案 B：雙模式（config flag `filter: "blacklist" | "whitelist"`）

### 尚未決定
- command grammar：是否支援帶參數的允許規則（如 `ls *` 但不允許 `ls /etc`）
- 可變參數模板（如允許 `cat <workspace 下任意路徑>`）
- 介面變更：`agent-gateway.sh` 的設定區段是否抽出為獨立 config 檔

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

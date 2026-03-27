---
date: 2026-03-27
session: agent-ssh-gateway P8.1 完成 + P8.2 設計
status: P8.1 Done / P8.2 Draft
generated: 2026-03-27 手動更新
---

# 最新交接文件 — AI Agent SSH Gateway

## Phase 狀態總覽

| Phase | 名稱 | 狀態 |
|-------|------|------|
| P1–P5 | SSH Gateway + Playwright + Runner | ✅ Done |
| P6 | n8n Job Trigger | ✅ Done |
| P7 | 分級風控（enforce 上線） | ✅ Done（2026-03-27 封版）|
| P7.1 | audit 觀察期 + rm pattern 修正 | ✅ Done |
| P7.2 | enforce 正式上線 + rollback drill | ✅ Done |
| P8 | AUTH_EXPIRED runner 端 | ✅ Done |
| P8.1 | Telegram 通知（n8n native node）| ✅ Done（2026-03-27）|
| P8.2 | TG 雙向指令頻道（daemon 方案）| 🔵 Draft，設計完成待實作 |
| P9 | 多主機支援 | 📝 Draft |

---

## 當前事實（已驗證）

### 部署狀態
- 部署路徑：`/usr/local/bin/` — `agent-gateway.sh`、`gateway-policy.sh`、`agent-switch`
- `GATEWAY_MODE=enforce`（正式生效）
- Log：`/Users/agentbot/logs/agent-ssh.log`

### Telegram Bot（P8.1）
| 項目 | 值 |
|------|-----|
| Bot username | `@Qwekdbjsjw_bot` |
| Bot ID | `8569580187` |
| Token | 存於 `.secrets.json`（gitignored）|
| Chat ID | `1469326872`（Ryan @RYN1491）|
| n8n Credential | `Agent SSH Gateway Bot`（id: `t5ML2WeYvrnTvenU`，type: `telegramApi`）|

### n8n Workflows

| ID | 名稱 | 狀態 |
|----|------|------|
| `SHhtbahAm28jNVVJ` | AUTH_EXPIRED 通知 (P8.1) | ✅ active |
| `RgpDAHpX723AfTbv` | TG 指令頻道 (P8.2) | ⚠️ inactive（需 HTTPS）|
| `Jrypa0wEQ0deyZBp` | n8n Job Trigger (P6) | ⚠️ inactive |

### P8.1 E2E 驗收（2026-03-27）
| 測試 | 結果 |
|------|------|
| POST /webhook/auth-expired | ✅ Workflow started |
| Code node 格式化 | ✅ |
| Telegram native node 送出 | ✅ 實際收到 HTML 格式通知 |
| 非阻塞 | ✅ runner exit code 不受影響 |

---

## P8.2 設計（下一個 AI 直接實作）

### 問題
n8n TelegramTrigger activate 失敗：`bad webhook: An HTTPS URL must be provided`

### 解法：`agent-tg-daemon.sh`（agentbot 上的 polling daemon）

優點：不需 HTTPS、不需 n8n、指令審核複用 gateway-policy.sh

**核心邏輯草稿**：
```bash
TOKEN="8569580187:AAGWHAt0Lq-SMK6gh8CyvFBP82aBP11CHOk"
CHAT_ID="1469326872"   # 只接受此 chat_id 的指令
OFFSET=0

while true; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates?offset=${OFFSET}&timeout=5")
  # 解析 text，過濾 chat_id，通過 gateway-policy 審核，執行，sendMessage 回應
  sleep 1
done
```

**支援指令**：
- `/status` → tail /Users/agentbot/logs/agent-ssh.log
- `/jobs` → ls /Users/agentbot/jobs/failed/
- `/requeue <job_id>` → 顯示指令（二次確認後執行）
- `/help` → 列指令

**部署步驟**：
1. 寫 `agent-tg-daemon.sh`
2. `sudo cp` 到 `/usr/local/bin/` + chmod 755
3. 寫 launchd plist 到 `/Library/LaunchDaemons/com.agentbot.tg-daemon.plist`
4. `sudo launchctl load` 常駐
5. Telegram 傳 `/help` E2E 驗收

---

## 重要已知事實

- `agent-switch status` 在非 agentbot 身份下顯示 UNKNOWN（正常，`.ssh/` 是 drwx------）
- LINE Notify 已死（2025-03-31）
- n8n Docker 連 host 用 `host.docker.internal`，不是 `127.0.0.1`
- n8n Code node 沙箱無 `process.env`

## 絕對不能動（P7 封版）

- `/usr/local/bin/agent-gateway.sh`
- `/usr/local/bin/gateway-policy.sh`
- `/usr/local/bin/agent-switch`
- `GATEWAY_MODE=enforce`
- Job schema

---

## 下一個 AI 的任務

**優先**：實作 `agent-tg-daemon.sh`（設計已完成，直接寫）

不要做：
- 不要改 P7 封版
- 不要啟用 `RgpDAHpX723AfTbv`（需 HTTPS）
- 不要重評估通知方案（已定案 Telegram + daemon）

---

## 核心路徑

| 項目 | 路徑 |
|------|------|
| Repo | `/Users/ryan/meta-agent/tools/agent-ssh-gateway/` |
| Runner config | `runner/runner.config.json` |
| Secrets | `.secrets.json`（gitignored）|
| Jobs | `jobs/{incoming,running,done,failed}/` |
| Gateway log | `/Users/agentbot/logs/agent-ssh.log` |
| n8n | `http://localhost:5678` |

---
date: 2026-03-27
session: agent-ssh-gateway P8.2 daemon 部署中
status: P8.1 Done / P8.2 In Progress（daemon 跑起，3 個 bug 待修）
generated: 2026-03-27 22:10 更新
---

# 最新交接文件 — AI Agent SSH Gateway

## Phase 狀態總覽

| Phase | 名稱 | 狀態 |
|-------|------|------|
| P1–P5 | SSH Gateway + Playwright + Runner | ✅ Done |
| P6 | n8n Job Trigger | ✅ Done |
| P7 | 分級風控（enforce 上線） | ✅ Done（封版）|
| P7.1 | audit 觀察期 + rm pattern 修正 | ✅ Done |
| P7.2 | enforce 正式上線 + rollback drill | ✅ Done |
| P8 | AUTH_EXPIRED runner 端 | ✅ Done |
| P8.1 | Telegram 通知（n8n native node）| ✅ Done（2026-03-27）|
| **P8.2** | **TG 雙向指令頻道（daemon 方案）** | 🟡 **In Progress — daemon 運行，3 bug 待修** |
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

## P8.2 現況（2026-03-27 22:10）

### 已完成部署
- `agent-tg-daemon.sh` 部署至 `/usr/local/bin/`
- launchd plist：`~/Library/LaunchAgents/com.agentbot.tg-daemon.plist`
- **pid=65089，exit code=0，持續運行中**
- `/status` 指令 → 手機正常收到回覆 ✅
- `/help` 指令 → 正常 ✅

### 已驗收
| 指令 | 結果 |
|------|------|
| `/start` | ✅ |
| `/status` | ✅ SSH Gateway Status 格式正確 |
| `/help` | ✅ |

### 3 個已知 Bug（待修）

| # | Bug | 症狀 | 優先 |
|---|-----|------|------|
| 1 | `/jobs` 空訊息 | `400 Bad Request: message text is empty` | 🔴 高 |
| 2 | `\n\n` 字面顯示 | Unknown command 回覆不換行 | 🟡 中 |
| 3 | 孤立子程序 | 每次 reload 後殘留 bash 子程序 | 🟡 中 |

### 下一個 AI 直接修

**Bug 1 — `/jobs` 空訊息**：
```bash
# agent-tg-daemon.sh 的 /jobs dispatch 段
# 問題：jobs 目錄空或格式化輸出為空字串，sendMessage 送空
# 修法：加 fallback「No jobs found」
```

**Bug 2 — `\n` 換行**：
```bash
# 把 "...\n\n..." 改為 $'...\n\n...'
```

**Bug 3 — 孤立子程序**：
```bash
# 在 daemon 頂部加 trap：
trap 'kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT
```

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

**優先**：修 P8.2 的 3 個 bug（見上方清單），優先 Bug 1 `/jobs` 空訊息

不要做：
- 不要改 P7 封版
- 不要啟用 `RgpDAHpX723AfTbv`（需 HTTPS）
- 不要重評估通知方案（已定案）
- 不要重新部署 daemon（已部署，直接改 source 重新 cp + reload）

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

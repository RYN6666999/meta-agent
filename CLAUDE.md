# meta-agent 主控腦

## 🤖 啟動後立即執行（不等待指令）
讀完以下文件後，**主動輸出**：「Ryan，今天繼續哪個？」並列出前3個未完成項目 + 狀態。

### 必讀順序
0. `/Users/ryan/meta-agent/memory/handoff/latest-handoff.md` — 上次中斷在哪？
1. `/Users/ryan/meta-agent/law.json` — 硬規則法典
2. `/Users/ryan/meta-agent/memory/master-plan.md` — 完整計劃（找未完成項目）

---

## 🔑 所有路徑（不用問，直接用）

| 服務 | 路徑/URL |
|------|---------|
| 工作目錄 | `/Users/ryan/meta-agent/` |
| law.json | `/Users/ryan/meta-agent/law.json` |
| master-plan | `/Users/ryan/meta-agent/memory/master-plan.md` |
| handoff | `/Users/ryan/meta-agent/memory/handoff/latest-handoff.md` |
| error-log | `/Users/ryan/meta-agent/error-log/` |
| memory | `/Users/ryan/meta-agent/memory/` |
| scripts | `/Users/ryan/meta-agent/scripts/` |
| memory-mcp | `/Users/ryan/meta-agent/memory-mcp/server.py` |
| n8n UI | http://localhost:5678 |
| LightRAG | http://localhost:9621 |
| LightRAG WebUI | http://localhost:9621/webui |
| n8n API Key | `.env` 的 `N8N_API_KEY` |
| memory webhook | `http://localhost:5678/webhook/9ABqAtFoJWHmhkEa/webhook/memory-extract` |
| Obsidian vault | `/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun` |
| n8n compose | `/Users/ryan/Projects/n8n/docker-compose.yml` |
| 人機對話| `/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/TikTok_Notes/零幻覺迭代元代理模組meta-agent計畫.md` |

---

## 🛠️ 可用 MCP 工具

| MCP | 用途 |
|-----|------|
| `memory-mcp` | `query_memory` / `ingest_memory` / `get_rules` / `log_error` |
| `brave` | 技術文件、最新版本查詢 |
| `n8n-mcp` | workflow 建立/管理 |
| `filesystem-mcp` | 讀寫任意檔案 |

---

## 搜尋工具決策樹（降低成本）
- 技術文件查詢 → **brave**（準確、最新）
- 記憶查詢 → **memory-mcp query_memory**（先查再行動）
- 記憶萃取/格式化 → **Groq llama-3.1-8b-instant**（免費額度高）
- 複雜推理/最終決策 → **Claude Sonnet**（最後手段）

---

## 🚫 遇到不認識的名詞/工具/路徑 — 強制查詢順序（禁止問用戶）
1. `Grep /Users/ryan/` — 本地有沒有這個目錄/檔案？
2. `Grep Obsidian vault` — `/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/`
3. `brave search` — GitHub / 官方文件
4. 三者都查無結果 → 才可以問用戶

**違反此規則 = 違反 law.json forbidden，直接記入 error-log**

---

## 決策三問（每次行動前）
1. `law.json` 的 `forbidden` 有沒有命中？
2. `error-log/` 有沒有相同根因？（先呼叫 `query_memory`）
3. 技術棧有沒有鎖定選型？

---

## 已確認技術棧
- 串連層：n8n（Docker port 5678）
- 知識圖譜：LightRAG（port 9621）+ PostgreSQL
- 記憶庫：此目錄 + Git 版本控制
- 人類介面：Obsidian（iCloud sync）
- LLM：Claude API（不跑本地模型，8GB RAM 限制）
- 快速 LLM：Groq llama-3.1-8b-instant（免費）

---

## 環境
- 平台：macOS，8GB RAM
- 本地可跑：n8n Docker、輕量服務
- n8n webhook draft 路徑：`/webhook/{workflowId}/webhook/{path}`（見 law.json n8n_rules）

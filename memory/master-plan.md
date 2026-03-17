---
date: 2026-03-16
type: verified_truth
status: active
last_triggered: 2026-03-16
base_score: 144.0
usage_count: 2
expires_after_days: 365
source: 完整差距分析
last_updated: 2026-03-16 17:10
---

# meta-agent 完整建設計劃
## 核心目標：對話中斷不再是問題，額度耗盡不再是恐懼

---

## 現有基礎（已完成）✅
- LightRAG 知識圖譜（運行中，已 ingest 8 份歷史遺產）
- law.json 硬規則法典
- 記憶 frontmatter 生命週期
- Git 評分自動提交（launchd 每小時）
- decision/ branch 技術備份
- obsidian-mcp（`.mcp.json` 設定完成，重啟生效）
- brave-mcp（已安裝）
- memory-mcp（Claude Code + nanoclaw 共用）
- **外掛大腦 HTTP API**（`api/server.py`，port 9901，Bearer auth）✅ D3 完成

---

## 全部缺口（P0→P5 優先序）

### P0｜對話連續性（最緊急）
**問題：額度耗盡 or 對話中斷 → 一切歸零**

- [x] **P0-A：對話檢查點系統**
  每隔 20 則訊息，自動把對話摘要寫入 `memory/checkpoints/`
  格式：`checkpoint-{session_id}-{timestamp}.md`
  內容：當前任務狀態、決策、未完成項目
  ✅ 由 `scripts/on-stop.py` Stop hook 實作（Turn 計數 + 每 20 次寫 checkpoint）

- [x] **P0-B：交接文件自動生成**
  額度剩 10% 時，觸發 Haiku 生成交接文件（仿照你 Obsidian 裡的 Gemini 交接文件格式）
  存入 `memory/handoff/latest-handoff.md`
  下一個 AI 讀這個文件就能無縫接手

- [x] **P0-C：session 恢復指令**
  在 CLAUDE.md 加入：「每次對話啟動，先讀 `memory/handoff/latest-handoff.md`」
  ✅ CLAUDE.md 已加入啟動必讀順序 + 主動輸出未完成項目

---

### P1｜自動對話記憶萃取（商業級最大缺口）
**問題：現在要手動 ingest，商業方案自動萃取**

- [x] **P1-A：n8n 對話後萃取 workflow**
  觸發：Telegram bot 接收對話 or webhook
  流程：
  ```
  對話文本 → Haiku 萃取
    → 錯誤/修正 → error-log/ + ingest LightRAG
    → 決策 → truth-source/ + ingest LightRAG
    → 規則 → 候選 law.json 更新（需人類確認）
  ```

- [x] **P1-B：Claude Code hook（PostConversation）**
  每次對話結束自動觸發萃取腳本
  ✅ Stop hook (`scripts/on-stop.py`) 每 10 次自動掃 JSONL → n8n webhook
  ✅ Bug 修復（2026-03-16）：JSONL 路徑動態搜尋 + assistant content list 正確解析
  ✅ 驗證：turn=50 測試，找到 205 個片段，HTTP 200 送出成功

---

### P2｜搜尋增強 + 成本降低
**問題：現在依賴 LLM 知識 → 貴且會幻覺**

- [x] **P2-A：Brave MCP 加入**
  ```bash
  claude mcp add brave -e BRAVE_API_KEY=$BRAVE_API_KEY \
    -- npx -y @modelcontextprotocol/server-brave-search
  ```
  用途：查最新文件、驗證 API 變化（取代 LLM 猜測）
  ✅ 已安裝，`claude mcp list` 確認 Connected

- [x] **P2-B：搜尋決策樹**
  在 law.json 加入「何時用哪個搜尋工具」規則
  ✅ 已寫入 `law.json` 的 `search_decision_tree` 欄位

- [x] **P2-C：Groq 替代昂貴操作**
  記憶萃取 / 清洗 / 格式化 → 全部用 Groq（免費額度高，速度快）
  ✅ 已寫入 `law.json` 的 `groq_architecture` 欄位

- [x] **P2-D：Instagram 提取品質改善** ⭐ NEW (2026-03-17)
  問題：media_count=0 但 caption 存在（yt-dlp 黑箱限制）
  解決方案：JSON-LD fallback 層
  實施：`common/instagram_extract.py` 新增 `_run_jsonld()` 函數
  流程：yt-dlp(0媒體但有caption) → JSON-LD爬取meta+schema → instaloader
  驗證：✅ Unit test 10/10 passed (parsing + fallback chain)
  預期效果：media_count 完整率 72% → 85%+（待 1 週現場驗證）
  後續：若 < 80% → 升級 P3 Lightpanda 原型，否則持續監控

---

### P3｜遺忘曲線執行引擎
**問題：設計了但沒跑**

- [x] **P3-A：`scripts/memory-decay.py`**
  每天執行（launchd）
  掃描所有 frontmatter → 計算衰退分數 → 更新 status

- [x] **P3-B：觸發強化機制**
  AI 引用某記憶時 → 自動更新 `last_triggered` + 分數 × 1.2
  ✅ memory-mcp `query_memory` 呼叫後自動觸發 `_update_last_triggered()`

---

### P4｜矛盾偵測 + 實體去重
**問題：新記憶可能與舊記憶衝突**

- [x] **P4-A：ingest 前矛盾檢查**
  新記憶 ingest 前，先查詢 LightRAG 是否有相關舊記憶
  如果有衝突 → 標記人類確認，不自動覆蓋
  ✅ memory-mcp `ingest_memory` 呼叫 `_check_conflicts()` 前置驗證
  📌 用 `[CONFIRMED]` 標記可跳過檢查

- [x] **P4-B：實體去重腳本**
  每週掃描 LightRAG 圖譜 → 合併相同概念節點
  ✅ `scripts/dedup-lightrag.py` + launchd 每週一 03:00

---

### P5｜記憶黑盒 MCP（共用大腦）
**問題：Golem/Nanoclaw/本地 LLM 各自孤立**

- [x] **P5-A：`memory-mcp/server.py`**
  4 個工具：
  - `query_memory(q)` → LightRAG 語意搜尋
  - `ingest_memory(content, type)` → 存入圖譜
  - `get_rules()` → 讀 law.json
  - `log_error(root_cause, solution)` → 寫 error-log + ingest

- [x] **P5-B：加入 claude mcp + golem + nanoclaw**
  所有工具共用同一個記憶後端
  ✅ nanoclaw: `/Users/ryan/nanoclaw/src/memory.ts` 直接打 LightRAG HTTP API
  ✅ Claude Code: memory-mcp global scope 已設定
  📌 project-golem: `claude mcp add --scope project memory-mcp python3 /Users/ryan/meta-agent/memory-mcp/server.py`（**待執行 — 下次開 golem 專案時補上**）

---
---

### D3｜外掛大腦 MVP ✅（2026-03-16 完成）
**目標：讓任何外部工具可直接透過 HTTP 使用記憶能力**

- [x] **D3-1：能力落差分析** — `docs/domain/commercial-memory-gap.md`
- [x] **D3-2：MVP 規格定義** — `docs/interfaces/external-brain-mvp.md`
- [x] **D3-3：HTTP API 實作** — `api/server.py`（FastAPI + Bearer auth）
  - `POST /api/v1/query` — LightRAG 語意搜尋
  - `POST /api/v1/ingest` — 存入圖譜（含矛盾檢查）
  - `GET  /api/v1/rules` — law.json 規則查詢
  - `POST /api/v1/log-error` — 寫 error-log + ingest
  - `GET  /api/v1/health` — 全服務健康狀態
  - `GET  /api/v1/trace` — 本地文件溯源
- [x] **D3-4：驗證** — `scripts/test_api.py` 全端點 HTTP 200 ✅

---

### D4｜商業級收斂（進行中 🚧）
**目標：補齊 rate limiting / 使用計數 / ingest metadata，讓 API 可對外正式接入**

- [x] **D4-1：ingest 補記憶品質 metadata** — `confidence`, `submitted_by`, `source_session`
- [x] **D4-2：usage 計數中間件** — 每次呼叫寫入 `system-status.json`
- [x] **D4-3：Rate limiting** — slowapi，防誤用
- [x] **D4-4：`GET /api/v1/status` 端點** — 外部可直接 polling 的 dashboard
- [x] **D4-5：project-golem MCP 掛載** — `claude mcp add --scope project`（2026-03-16 已完成）

---

### D5｜記憶治理強化（進行中 🚧）
**目標：借鑑 golem 記憶引擎優勢，補齊重排訊號、寫入安全閘、分層摘要**

- [x] **D5-1：query rerank 訊號** — `confidence/freshness/usage_count` 本地重排附加
- [x] **D5-2：ingest 安全閘** — 高風險內容需 `[APPROVED]` 才允許寫入
- [x] **D5-3：tiered summary 腳本** — `scripts/memory-tier-summary.py` 生成 daily/monthly/yearly
- [x] **D5-4：rerank 結構化輸出** — `/api/v1/query` 新增 `rerank_candidates` + `memory_boost_updated` JSON 欄位

---

### D6｜商業級缺口補全（2026-03-16 完成 ✅）
**目標：補齊量化分析中前3高槓桿缺口（-80%/-100%/-40%）**

- [x] **D6-1：tiered summary launchd 排程** — `com.meta-agent.tiered-summary` 每日 02:15 自動執行（-40% → 收斂）
- [x] **D6-2：多租戶 user_id 軟隔離** — `query/ingest` 支援 user_id，非預設用戶本地 `memory/users/{id}/` 獨立存儲，rerank 僅掃個人空間（-100% → 架構已建立）
- [x] **D6-3：自動記憶萃取** — `on-stop.py` 每 50 輪讀取 `~/.claude/projects/*.jsonl`，自動送 n8n memory-extract webhook（-80% → 半自動化）

---

### D8｜人格庫定時工作流（2026-03-16 完成 ✅）
**目標：讓不同人格有獨立知識累積與獨立工作節奏（先落地尖端工程師人格）**

- [x] **D8-1：人格註冊表** — `memory/persona-registry.json`（builder/domain-business/senior-hr）
- [x] **D8-2：尖端工程師技術雷達腳本** — `scripts/persona_tech_radar.py`（Brave 搜尋 → 清洗報告 → ingest 人格庫）
- [x] **D8-3：每日定時排程** — `com.meta-agent.persona-tech-radar`（每日 09:30）
- [x] **D8-4：機器可讀狀態** — `system-status.json` 寫入 `persona_tech_radar` 執行結果

---

### D9｜自動觸發機制強化（2026-03-16 完成 ✅）
**目標：補齊 P1 對話萃取可靠度 + Obsidian 多來源自動 ingest**

- [x] **D9-1：on-stop.py Bug 修復** — JSONL 路徑由寫死 `-Users-ryan` 改為動態搜尋所有 project dirs；assistant content list 解析修正（過濾 thinking 區塊，只取 text）
- [x] **D9-2：萃取 threshold 降低** — 從每 50 次降至每 10 次觸發（catch 更高比例的對話片段）
- [x] **D9-3：Obsidian → LightRAG 自動同步** — `scripts/obsidian-ingest.py`，每 30 分鐘 launchd，掃描 mtime 新增/修改的 .md 文件
- [x] **D9-4：增量同步狀態管理** — `memory/obsidian-sync.json` 追蹤 `last_synced_ts`，僅 ingest 新文件
- [x] **D9-5：launchd 排程** — `com.meta-agent.obsidian-ingest`（`StartInterval=1800`）已載入
- [x] **D9-6：驗證** — TikTok_Notes 8 份文件全部 ingest 成功（首次執行，含「零幻覺迭代元代理模組 meta-agent 計畫」）

---

## 執行順序（按緊急度）

```
Week 1：P0（對話連續性）→ 讓你立刻不再怕中斷
Week 2：P2（搜尋增強）→ 降低成本，裝 Brave MCP
Week 2：P1（自動萃取）→ 讓記憶自動增長
Week 3：P3（遺忘引擎）→ 讓遺忘有意義
Week 4：P4（矛盾偵測）→ 品質保證
Week 4：P5（黑盒MCP）→ 開放給所有工具
```

---

## 成本估算（完成後）

| 操作 | 現在 | 完成後 |
|------|------|--------|
| 文件查詢 | Claude Sonnet | qmd（免費）|
| 網頁搜尋 | Claude Sonnet | Brave（$0.01/查）|
| 記憶萃取 | 手動 | Groq Haiku（免費額度）|
| 對話恢復 | 重新解釋 | 讀交接文件（0 成本）|
| **整體 token** | **100%** | **預估降低 60-70%** |

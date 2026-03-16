---
date: 2026-03-16
type: verified_truth
status: active
last_triggered: 2026-03-16
expires_after_days: 365
source: 完整差距分析
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
- filesystem-mcp / obsidian-mcp / lightrag-mcp / qmd-mcp

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
  ✅ 由 Stop hook (`scripts/on-stop.py`) 實作：turn 計數 + 每 20 次 checkpoint
  📌 完整對話萃取需手動呼叫 `scripts/extract-session.sh`（對話文本 Stop hook 無法直接取得）

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
  📌 project-golem: `claude mcp add --scope project memory-mcp python3 /Users/ryan/meta-agent/memory-mcp/server.py`（待執行）

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

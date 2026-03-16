---
date: 2026-03-16
type: error_fix
status: active
last_triggered: 2026-03-16
base_score: 120.0
expires_after_days: 730
topic: agent-behavior-bugs
severity: critical
source: 用戶直接回報
---

# Agent 行為 Bug（用戶抱怨）

## BUG-1：不知道就問用戶，而不是先用工具查

**現象**：不認識 "nanoclaw" → 直接問用戶「nanoclaw 是什麼？」
**根本原因**：沒有執行「查詢優先」原則。可用的工具有：brave search、Obsidian vault 掃描、GitHub 搜尋、本地檔案系統搜尋。應先窮盡工具再問。
**影響**：讓用戶重複解釋已有文件記載的事情，浪費用戶時間。
**正確行為**：
1. 先用 `Grep` 掃本地 `/Users/ryan/` 目錄
2. 再查 Obsidian vault（`/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/`）
3. 再用 brave/WebSearch 搜 GitHub
4. 以上全找不到才問用戶

**修正規則**：「能用工具查到的問題，禁止問用戶」— 加入 law.json forbidden

---

## BUG-2：自己設計的三重查詢規則自己不執行

**現象**：law.json 和 CLAUDE.md 都有 `search_decision_tree`，規定「先查 memory-mcp → brave → Groq」，但實際行動時直接問用戶而跳過所有查詢。
**根本原因**：規則寫在文件裡，但每次啟動沒有強制自我檢查機制。Phase 2 執行前沒有走決策三問。
**影響**：系統設計形同虛設，token 浪費，用戶信任損失。
**正確行為**：每次遇到「不確定的概念/名詞/路徑」時，強制觸發查詢流程，不走捷徑問人。

**修正規則**：加入 law.json forbidden「禁止在未窮盡工具前問用戶已有文件記載的問題」

---

## BUG-3：設計了工具但不主動調用

**現象**：memory-mcp `query_memory`、brave search 都已裝好，但遇到問題時沒有主動呼叫。
**根本原因**：沒有把「行動前先查」內化為反射動作，而是把工具當成「被要求才用」的功能。
**正確行為**：任何不確定的輸入（人名、工具名、路徑、概念）→ 立即觸發查詢，不等指令。

---

## 修正方案

1. ✅ 在 law.json `forbidden` 加入強制規則
2. ✅ 在 CLAUDE.md 加入「遇到不認識的名詞必做」checklist
3. 行為層面：每次看到不熟悉的名詞 → 反射性觸發 Grep + brave，不問用戶

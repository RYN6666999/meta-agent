---
project: crm-memory-mvp
phase: 1
status: planning
created: 2026-03-27
last_updated: 2026-03-27
owner: Ryan
priority: P1
---

# CRM Agent 記憶系統 — Phase 1 MVP 追蹤板

## 北極星
讓 fdd-crm AI 助理從「單輪失憶」升級成「跨對話持久記憶」。
不依賴本機，只靠 Cloudflare KV。

## 當前狀態
```
規劃完成 → Batch A 待開始
```

---

## Batch 執行板

### Batch A｜資料層 ← 下一個開始
**目標：** schema 定稿 + Cloudflare KV CRUD API 可用

| Task | 狀態 | 說明 |
|------|------|------|
| A1 記憶 schema 定稿 | ⬜ todo | id/type/subject/summary/keywords/pinned/archived/usageCount/timestamps/source |
| A2 KV key 命名規則 | ⬜ todo | `mem:{userId}:{id}` 或 `mem:{id}` |
| A3 GET /api/memories | ⬜ todo | 支援 subject / type 篩選 |
| A4 POST /api/memories | ⬜ todo | 新增記憶 |
| A5 PUT /api/memories/:id | ⬜ todo | 更新 pinned / content |
| A6 DELETE /api/memories/:id | ⬜ todo | 軟刪除（archived=true） |
| A7 POST /api/memories/retrieve | ⬜ todo | 傳入 message → Top 5 |

**DoD：** curl 可打通所有 API，KV 讀寫正常

---

### Batch B｜前端服務層
**目標：** memory service 封裝 + 評分檢索可用

| Task | 狀態 | 說明 |
|------|------|------|
| B1 memory service 封裝 | ⬜ todo | listMemories / createMemory / updateMemory / deleteMemory |
| B2 retrieveRelevantMemories() | ⬜ todo | keyword × 0.4 + freshness × 0.3 + usage × 0.2 + type × 0.1 |
| B3 pinned 加權邏輯 | ⬜ todo | pinned 直接進 Top 5 |
| B4 token 截斷保護 | ⬜ todo | 注入總長 < 500 token |

**DoD：** `retrieveRelevantMemories("王小明下週聯繫")` 回傳正確 Top 5

---

### Batch C｜AI 注入與自動萃取
**目標：** AI 真正開始「有記憶」+ 自動學習

| Task | 狀態 | 說明 |
|------|------|------|
| C1 buildSystemPrompt() 注入記憶 | ⬜ todo | Top 5 以結構化文字注入 |
| C2 注入失敗 graceful fallback | ⬜ todo | KV 錯誤不中斷聊天 |
| C3 對話後非同步萃取記憶 | ⬜ todo | 用現有 AI 供應商，抽 1-3 條 JSON |
| C4 萃取結果去重後寫入 | ⬜ todo | summary 相似度 > 80% 不重複寫 |
| C5 萃取失敗不影響主回應 | ⬜ todo | try/catch 隔離 |

**DoD：** 第二次問同一客戶，system prompt 裡看得到上輪 episode

---

### Batch D｜最小 UI + 驗收
**目標：** 可觀察、可修正、手機可用

| Task | 狀態 | 說明 |
|------|------|------|
| D1 AI 頁記憶側欄或展開區 | ⬜ todo | 顯示近期記憶列表 |
| D2 手動新增記憶 | ⬜ todo | 一句話輸入框 |
| D3 刪除記憶 | ⬜ todo | 單筆刪除 |
| D4 釘選記憶 | ⬜ todo | toggle pinned |
| D5 手機 UI 驗證 | ⬜ todo | ≤ 3 步操作 |
| D6 全流程 E2E 驗收 | ⬜ todo | 見下方 DoD |

**DoD（全 Phase 1）：**
- [ ] 新增一條記憶後，重整頁面仍存在
- [ ] 對同客戶第二次提問，system prompt 含該 episode
- [ ] 對話後自動抽出 ≥ 1 條有效記憶
- [ ] UI 可刪除、釘選記憶
- [ ] 關掉本機，功能仍正常

---

## 執行規則

### 每個 Batch 開始前
1. 讀本檔，確認當前 Batch 狀態
2. 讀 `handoff-current.md`，接上上次斷點

### 每個 Batch 完成後（強制）
```bash
# 1. 更新本檔 Task 狀態（⬜→✅）
# 2. 寫 Batch 交接
cp handoff-template.md handoff-batch-X.md
# 3. bug closeout（如有修過 bug）
python3 /Users/ryan/meta-agent/scripts/bug_closeout.py ...
# 4. commit
git add tools/crm/ && git commit -m "feat(crm-memory): Batch X complete - ..."
# 5. deploy
npx wrangler pages deploy . --project-name fdd-crm --commit-dirty=true
# 6. 更新 handoff-current.md 指向下一個 Batch
```

### 狀態符號
| 符號 | 意思 |
|------|------|
| ⬜ | todo |
| 🔵 | in progress |
| ✅ | done |
| ❌ | blocked，附原因 |
| ⏭ | skipped，附理由 |

---

## 關鍵約束（不可違反）

- ❌ 不碰 LightRAG / localhost / SSH / n8n（Phase 2 以後）
- ❌ 不引入前端框架
- ❌ 不把全部記憶 dump 進 prompt
- ❌ 不重寫整個 crm.js
- ✅ 每次 Batch 完成必須 deploy + 驗收才能繼續下一個

---

## 快速路徑

```
CRM 目錄：     /Users/ryan/meta-agent/tools/crm/
KV 綁定：      FDD_LOGINS（現有）→ 需新增 CRM_MEMORIES
函式目錄：     /Users/ryan/meta-agent/tools/crm/functions/api/
OpenAPI 規格： /Users/ryan/meta-agent/memory/projects/crm-memory-mvp/openapi.yaml  ← 中斷後先讀這個
設計文件：     /Users/ryan/meta-agent/memory/crm-agent-memory-design-brief.md
Handoff 模板： /Users/ryan/meta-agent/memory/projects/crm-memory-mvp/handoff-template.md
```

## 中斷恢復 SOP

任何 AI 接手時，依序讀：
1. `openapi.yaml` → 了解 API 合約與資料模型
2. `plan.md`（本檔）→ 找當前 Batch，找第一個 ⬜
3. `handoff-batch-X.md`（如有）→ 上次斷點細節
4. 直接從第一個 ⬜ task 開始，不要重新規劃

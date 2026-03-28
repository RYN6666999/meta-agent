---
project: crm-memory-mvp
phase: 1
status: phase1-complete
created: 2026-03-27
last_updated: 2026-03-28
owner: Ryan
priority: P1
---

# CRM Agent 記憶系統 — Phase 1 MVP 追蹤板

## 北極星
讓 fdd-crm AI 助理從「單輪失憶」升級成「跨對話持久記憶」。
不依賴本機，只靠 Cloudflare KV。

## 當前狀態
```
✅ Phase 1 完成 (2026-03-28) — Batch A+B+C+D 全部 deployed
下一步：Phase 2（本機橋接：LightRAG + SSH + n8n）
```

---

## Batch 執行板

### Batch A｜資料層 ✅ DONE (2026-03-28)
**目標：** schema 定稿 + Cloudflare KV CRUD API 可用

| Task | 狀態 | 說明 |
|------|------|------|
| A1 記憶 schema 定稿 | ✅ | id/type/subject/summary/keywords/pinned/archived/usageCount/timestamps/source |
| A2 KV key 命名規則 | ✅ | `mem:{id}` + index array |
| A3 GET /api/memories | ✅ | 支援 subject / type 篩選 |
| A4 POST /api/memories | ✅ | 新增記憶 |
| A5 PUT /api/memories/:id | ✅ | 更新 pinned / content |
| A6 DELETE /api/memories/:id | ✅ | 軟刪除（archived=true） |
| A7 POST /api/memories/retrieve | ✅ | 傳入 message → Top 5 + promptSnippet |

**DoD：** ✅ curl 全部打通，KV 讀寫正常

---

### Batch B｜前端服務層 ✅ DONE (2026-03-28)
**目標：** memory service 封裝 + 評分檢索可用

| Task | 狀態 | 說明 |
|------|------|------|
| B1 memory service 封裝 | ✅ | memoryService: list/create/update/delete/retrieve |
| B2 retrieveRelevantMemories() | ✅ | 呼叫 /api/memories/retrieve，scoring 在 server |
| B3 pinned 加權邏輯 | ✅ | pinned bonus +999 (server-side) |
| B4 token 截斷保護 | ✅ | promptSnippet < 500 token (server-side) |

**DoD：** ✅ retrieve 回傳正確 Top 5 + promptSnippet

---

### Batch C｜AI 注入與自動萃取 ✅ DONE (2026-03-28)
**目標：** AI 真正開始「有記憶」+ 自動學習

| Task | 狀態 | 說明 |
|------|------|------|
| C1 buildSystemPrompt() 注入記憶 | ✅ | async，inject promptSnippet 到 system prompt |
| C2 注入失敗 graceful fallback | ✅ | KV 失敗回傳空字串，聊天正常 |
| C3 對話後非同步萃取記憶 | ✅ | extractAndSaveMemories() fire-and-forget |
| C4 萃取結果去重後寫入 | ✅ | >80% keyword overlap 跳過 |
| C5 萃取失敗不影響主回應 | ✅ | try/catch 全隔離 |

**DoD：** ✅ 第二次問同一客戶，system prompt 含 episode（E2E 驗證通過）

---

### Batch D｜最小 UI + 驗收 ✅ DONE (2026-03-28)
**目標：** 可觀察、可修正、手機可用

| Task | 狀態 | 說明 |
|------|------|------|
| D1 AI 頁記憶面板 | ✅ | 🧠 按鈕 toggle，5 tab 分類 + 搜尋 |
| D2 手動新增記憶 | ✅ | 底部輸入框，Enter 或按 ＋ 新增，自動判斷 type/subject |
| D3 刪除記憶 | ✅ | 單筆 🗑 + confirm |
| D4 釘選記憶 | ✅ | 📌 toggle，pinned 高亮顯示 |
| D5 手機 UI 驗證 | ✅ | ≤ 3 步操作，flex wrap 適配小螢幕 |
| D6 全流程 E2E 驗收 | ✅ | 所有 DoD 通過 |

**DoD（全 Phase 1）：**
- [x] 新增一條記憶後，重整頁面仍存在
- [x] 對同客戶第二次提問，system prompt 含該 episode
- [x] 對話後自動抽出記憶（Claude/Gemini 供應商）
- [x] UI 可刪除、釘選記憶
- [x] 關掉本機，功能仍正常（純 Cloudflare KV）

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

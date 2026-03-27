# CRM Agent 記憶系統設計簡報
> 用途：丟給 AI 討論，不是最終決策文件
> 作者：Ryan + Claude Sonnet 4.6
> 日期：2026-03-27

---

## 一、專案背景

### 1.1 這是什麼

**fdd-crm**：一個部署在 Cloudflare Pages 的 PWA，給房地產銷售業務用的 CRM 系統。

功能模塊：
- 🌳 人脈樹（聯繫人節點、關係圖）
- 🎓 學員管理（三件套進度、聯繫時間軸）
- 📋 日報表 / 📅 日程 / 💰 業績 / 📁 文件
- 🤖 AI 助理（目前只有單輪對話 + 清除）

技術棧：
- 前端：純 HTML + CSS + Vanilla JS（無框架）
- 部署：Cloudflare Pages（靜態）+ Cloudflare Functions（API proxy）
- 儲存：localStorage（主）+ Cloudflare KV（登入）
- AI：多供應商切換（Claude / Gemini / Grok / OpenRouter / 自定義）

### 1.2 使用者畫像

**主要用戶：業務員（行動優先）**

典型一天：
```
早上出門前（手機）→ 問 AI 今天要跟進哪幾個？
拜訪中（手機）→ 剛講完電話，記錄結果
下午（手機）→ 這個客戶上次說什麼？
晚上（電腦）→ 複盤、請 AI 給建議
```

核心需求：
1. 任何裝置都能用（手機優先）
2. 3 秒內有上下文的回應
3. 一句話就能寫入記憶
4. 越用越了解我的風格與客戶

---

## 二、本地基礎設施（Ryan 的機器）

Ryan 本機已有一套成熟的 AI agent 基礎架構，可作為 CRM agent 的後端強化層：

### 2.1 核心組件

| 組件 | 位置 | 說明 |
|------|------|------|
| **LightRAG** | `localhost:9621` | 語意向量搜尋 + 知識圖譜，已含 Obsidian 筆記 |
| **memory-mcp** | `tools/memory-mcp/server.py` | FastMCP server，提供 `query_memory` / `ingest_memory` / `get_rules` |
| **n8n** | `localhost:5678` | 本地 workflow 引擎，可接 webhook |
| **Obsidian vault** | `iCloud/.../Documents/Fun` | 知識庫，30 分鐘自動 ingest 到 LightRAG |
| **local_memory_extract.py** | `scripts/` | 對話文字 → 結構化記憶 → LightRAG |
| **law.json** | repo 根目錄 | 硬性決策規則庫（禁止事項、技術棧規範） |
| **structured_memory.db** | `common/` | SQLite，4 種記憶類型：fact / preference / episode / task |

### 2.2 已有的記憶管線

```
Obsidian 筆記
    ↓ (每30分鐘 obsidian-ingest.py)
LightRAG 知識圖譜
    ↑
對話 → local_memory_extract.py → 結構化記憶
    ↑
bug 修復 → bug_closeout.py → truth-source + LightRAG
```

### 2.3 SSH 工具可用

Ryan 有 SSH 工具，可以：
- 直接操作本機腳本（觸發 memory_extract / ingest）
- 查詢 LightRAG REST API
- 觸發 n8n webhook
- 讀寫 Obsidian vault 檔案

這是關鍵：**SSH 橋接可以彌補「雲端 PWA 無法直接碰 localhost」的斷層。**

---

## 三、問題定義

### 3.1 現有 AI 助理的限制

```javascript
// 目前 crm.js 的 AI 記憶實作
chatHistory = []  // 單一全域陣列
// 重整頁面 = 記憶消失（只有當次 session）
// 沒有跨對話持久記憶
// 沒有 system prompt 個人化注入
// 沒有記憶管理 UI
```

**問題：每次開啟都是白紙，業務要重複解釋自己的客戶、話術偏好、目標。**

### 3.2 目標

- **靜態知識**：業務話術、產品知識、公司規則 → 每次對話都帶入
- **動態判斷框架**：從歷史對話中學習 Ryan 的決策模式 → 越來越精準
- **情境記憶**：「上次問 A 客戶要考慮 3 天」→ 下次自動帶入
- **記憶量可控**：不能把全部記憶都 dump 到 context（token 爆炸）

---

## 四、架構設計討論

### 4.1 方案 A（過度工程）❌

```
CRM → n8n webhook → memory-mcp → LightRAG
```

**問題**：
- 本機不在線 → 全部失效
- 手機訪問 → localhost 不可達
- 三層延遲 → 回應慢
- 維護複雜度高

### 4.2 方案 B（推薦方向）✅

**雙層架構：雲端為主，本機為強化**

```
Layer 1（永遠在線，雲端）：
  Cloudflare KV 記憶庫
  ├── fact      → 「Ryan 目標月業績 30 萬」
  ├── rule      → 「學員第一句話先問財務現況」
  ├── episode   → 「王小明 3/15 說下週再聯繫」
  └── style     → 「偏好簡短直接的話術」

Layer 2（本機在線時啟動）：
  LightRAG 語意搜尋 → 蓋過 KV 的 keyword 結果
  Obsidian 知識庫 → 靜態知識自動同步
```

**流程：**
```
用戶發訊息
    ↓
① 抽關鍵字（正則 / 簡單 NLP）
    ↓
② 記憶檢索
   ├─ 試打 localhost:9621（LightRAG）→ 有則用語意結果
   └─ 失敗 → 從 KV 做 keyword + 時間衰減排序
    ↓
③ Top 5 記憶注入 system prompt（< 500 token）
    ↓
④ 送 AI（OpenRouter / Claude / Gemini...）
    ↓
⑤ 回應後非同步寫入記憶
   ├─ 本機：SSH 觸發 local_memory_extract.py → LightRAG
   └─ 遠端：暫存 KV，等下次本機同步
```

### 4.3 記憶檢索策略

**不能全 dump，要智能選取：**

```
評分 = 關鍵字命中(40%) + 時間新鮮度(30%) + 使用頻率(20%) + 類型權重(10%)

類型權重：
  rule > fact > episode > style
  （規則最重要，風格最次要）

上限：Top 5 條 / 每次，總 token < 500
衰減：30天未使用的記憶降權，90天自動歸檔
```

### 4.4 記憶生命週期

```
新增：AI 對話後自動萃取 1-3 條 OR 用戶手動新增
更新：同類記憶衝突時覆蓋舊的（不累積矛盾）
歸檔：90天未觸發 → 移到 archive 不刪除
同步：本機在線時，KV 記憶 → LightRAG（雙向一致）
```

---

## 五、實作範圍

### Phase 1（核心，不依賴本機）
- [ ] Cloudflare KV 記憶庫 CRUD
- [ ] 記憶管理 UI（AI 頁新增側欄）
- [ ] System prompt 注入邏輯
- [ ] 對話後自動萃取記憶（用 AI 本身萃取）
- [ ] 記憶評分 + Top 5 選取

### Phase 2（強化，本機橋接）
- [ ] 本機 LightRAG 偵測（ping localhost:9621）
- [ ] SSH 觸發 memory_extract.py
- [ ] KV ↔ LightRAG 雙向同步
- [ ] Obsidian 靜態知識直接查詢

### Phase 3（迭代學習）
- [ ] 判斷框架提取（從多次對話歸納 Ryan 的決策模式）
- [ ] 記憶品質評分（準確率追蹤）
- [ ] 知識圖譜視覺化（在 CRM 內顯示）

---

## 六、技術約束

| 約束 | 說明 |
|------|------|
| CRM 是靜態 PWA | 不能跑後端，只能透過 fetch 打外部 API |
| Cloudflare Function 有 CPU 限制 | 不能跑複雜運算，只能做 proxy |
| localStorage 容量 | 約 5MB，記憶不能無限增長 |
| Cloudflare KV | 讀免費額度大，寫有限制（1000次/天 免費） |
| 手機優先 | UI 必須適配小螢幕，操作要少於 3 步 |
| 本機依賴是選配 | 本機關機不能影響核心功能 |
| 8GB RAM 限制 | **禁止在本機跑任何本地 LLM** |
| SSH 工具可用 | 可橋接本機腳本，是 Phase 2 的關鍵 |

---

## 七、討論問題清單

請 AI 協助討論以下問題：

**設計層面：**
1. 記憶評分策略有更好的設計嗎？（目前是 keyword + 時間衰減）
2. 「動態判斷框架」要怎麼從歷史對話中自動歸納？有哪些方法？
3. 記憶衝突（新舊矛盾）怎麼處理最穩健？

**技術層面：**
4. Cloudflare KV 做記憶庫的瓶頸在哪？有更好的雲端選擇嗎？
5. Phase 2 的 SSH 橋接，最簡單的實作方式是什麼？
6. 記憶 ↔ LightRAG 同步的一致性怎麼保證？

**產品層面：**
7. 業務場景下，記憶 UI 應該長什麼樣？（盡量少操作）
8. 「越用越聰明」的可觀測指標是什麼？怎麼讓用戶感受到？
9. 記憶量到 200 條之後，淘汰策略應該是什麼？

---

## 八、相關路徑速查

```
CRM 主程式：/Users/ryan/meta-agent/tools/crm/
  ├── index.html
  ├── crm.js      ← AI 相關：sendChat(), buildSystemPrompt(), AI_PROVIDERS
  └── crm.css

記憶基礎設施：/Users/ryan/meta-agent/
  ├── law.json                          ← 硬規則庫
  ├── memory/handoff/latest-handoff.md  ← 最新交接
  ├── scripts/local_memory_extract.py   ← 對話 → 記憶
  ├── scripts/obsidian-ingest.py        ← OB → LightRAG
  ├── tools/memory-mcp/server.py        ← MCP server
  └── common/memory_store.py            ← SQLite schema

外部服務：
  LightRAG: http://localhost:9621
  n8n:      http://localhost:5678
  CRM:      https://fdd-crm.pages.dev
```

---

*報告完。可直接丟給 AI 討論，建議從「七、討論問題清單」切入。*

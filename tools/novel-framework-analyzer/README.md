# Novel Framework Analyzer — 局心欲變小說分析系統

把中文小說切成場景，用「**局心欲變**」框架進行結構化 LLM 分析、標注與人工複審。

> **核心問題**：寧凡哪幾場談判最能代表他的厲害之處？他如何在弱勢中反拿主導權？

詳細 MVP 目標與成功標準見 [`docs/mvp-goal.md`](docs/mvp-goal.md)。

---

## 什麼是「局心欲變」框架

分析順序固定：**局 → 心 → 欲 → 變**

| 維度 | 說明 |
|------|------|
| **局**（Situation） | 外部賽局結構、權力非對稱、誰主動誰被迫 |
| **心**（Mind） | 此局催生的認知條件、盲區、System 1 vs System 2 張力 |
| **欲**（Desire） | 此局激活的顯性／隱性動機與欲望衝突 |
| **變**（Change） | 觸發事件、變前→變後的局勢相變、轉變類型與強度 |

每個場景輸出一張 `SceneFrameworkCard`，包含四維分析 + 原文引用。

---

## MVP 主要功能

- **書籍上傳** — 上傳 `.txt`，自動偵測章節數，支援 hash 去重
- **場景切分** — 正則切章 + 場景邊界偵測，角色名自動識別
- **局心欲變分析** — LLM 批次分析，JSON schema 驗證，支援斷點續跑
- **談判場景標記** — 自動識別談判場景，輸出 `negotiation_pattern_tags`
- **場景查詢** — 按角色／章節／談判旗標／標籤過濾
- **人工複審與修正** — 前端修正 AI 判斷，記錄 diff，支援「黃金樣本」標記

> 向量搜尋、MCP 工具介面、多模型路由、非虛構支援、費用儀表板等功能列為 deferred，見 [`docs/mvp-goal.md`](docs/mvp-goal.md)。

---

## 技術棧

### 後端

| 分類 | 技術 |
|------|------|
| **Web 框架** | [FastAPI](https://fastapi.tiangolo.com/) |
| **資料庫** | SQLite + [SQLAlchemy](https://www.sqlalchemy.org()) ORM |
| **資料驗證** | [Pydantic v2](https://docs.pydantic.dev/) |
| **HTTP 客戶端** | [httpx](https://www.python-httpx.org/)（非同步） |
| **Python** | 3.10+ |

### AI / LLM

| 分類 | 技術 |
|------|------|
| **LLM** | [OpenRouter](https://openrouter.ai/) → Claude Haiku / Sonnet |
| **Adapter 模式** | `AbstractLLMClient`，可替換為本地 Ollama 或 Gemini |

### 前端

| 分類 | 技術 |
|------|------|
| **前端** | 純 HTML + Vanilla JS（零依賴，`frontend/index.html`） |

---

## 架構概覽

```
txt 上傳
  ↓
SceneSplitter（正則切章 + 場景邊界偵測）
  ↓
CharacterExtractor（高頻人名自動識別）
  ↓
FrameworkAnalyzer（LLM 呼叫 + JSON schema 驗證）
  ↓
SceneFrameworkCard（SQLite 持久化）
  ↓
FastAPI REST API（port 8765）
  └── 前端 SPA（Upload / Scenes / Negotiation / Characters）
```

---

## 快速開始

### 安裝依賴

```bash
pip install -r requirements-mcp.txt
```

### 啟動服務

```bash
python3 server.py
# 前端 + REST API 在 http://localhost:8765
```

### 批次分析書籍

```bash
# 分析第 1–10 章
python3 scripts/batch_analyze.py --book-id <book_id> --start 1 --end 10

# 跳過已分析場景（斷點續跑）
python3 scripts/batch_analyze.py --book-id <book_id> --start 1 --end 10 --skip-existing
```

### 查詢場景（CLI）

```bash
python3 scripts/query.py --character 寧凡 --negotiation
```

---

## 前端分頁（MVP）

| 分頁 | 說明 |
|------|------|
| Upload | 書籍上傳 + 批次分析觸發 |
| Scenes | 場景列表 + 詳情 Modal（支援人工標注） |
| Negotiation | 談判場景（角色下拉過濾） |
| Characters | 角色清單 |

---

## 核心 API 端點（port 8765）

| Method | 路徑 | 說明 |
|--------|------|------|
| POST | `/api/upload` | 上傳書籍 |
| POST | `/api/analyze` | 觸發非同步批次分析 |
| GET | `/api/books` | 書籍清單 |
| GET | `/api/scenes` | 場景列表（支援多維過濾） |
| GET | `/api/scene/{ch}/{sc}` | 場景完整分析卡 |
| PATCH | `/api/scene/{ch}/{sc}/annotate` | 人工標注（含 diff 快照） |
| GET | `/api/negotiation` | 談判場景列表 |
| GET | `/api/characters` | 角色清單 |

---

## 資料夾結構

```
.
├── server.py              # FastAPI 主服務（port 8765）
├── backend/app/
│   ├── database.py        # SQLAlchemy 設定
│   ├── models/            # ORM 資料模型
│   ├── api/routes/        # REST API 路由
│   └── services/          # 業務邏輯
├── services/llm/          # LLM Adapters
├── scripts/               # 批次分析、查詢腳本
├── prompts/               # 局心欲變 LLM Prompt 範本
├── schemas/               # JSON Schema 驗證
├── frontend/index.html    # 前端 SPA
└── docs/                  # 架構文件與開發計畫
```

---

## 環境變數

```bash
OPENROUTER_API_KEY=sk-...          # OpenRouter API Key（必填）
DATABASE_URL=sqlite:///./novel_analyzer.db
```

---

## 開發計畫

- **Phase 1 (MVP)** — 上傳、切場景、分析、查詢、人工複審 ← 現在
- **Phase 2** — SmartRouter、角色弧線、費用追蹤、MCP 工具
- **Phase 3** — RAGFlow 知識庫、Dify workflow、微調數據集

詳見 [`docs/dev-plan.md`](docs/dev-plan.md) 與 [`docs/mvp-goal.md`](docs/mvp-goal.md)。

---

## 授權

MIT

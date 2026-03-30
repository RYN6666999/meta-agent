# 中文小說「局心欲變」框架分析系統 — 架構文件

## Data Flow 完整圖

```
小說匯入                   分析管線                   查詢介面
─────────               ─────────────              ──────────────

txt/pdf/docx             SceneSplitter              User Query
     │                        │                          │
     ▼                        ▼                          ▼
IngestService          [scene_text]              RetrievalRouter
     │                        │                    ┌────┴────┐
     ▼                        ▼                    ▼         ▼
RAGFlow (入庫)       FrameworkAnalyzer      SceneCard   RAGFlow
(chunk + embed)              │              Searcher    Vector
                             ▼              (PG)        Search
                     SceneFrameworkCard          │         │
                        Schema (JSON)            └────┬────┘
                             │                       ▼
                             ▼                  ResultMerger
                       PostgreSQL                    │
                    (framework_cards)                ▼
                             │               QueryResult[]
                             └──────────────→  (帶 source)
                                                    │
                                                    ▼
                                            Chat LLM Answer
                                           + source_references
```

## 模組責任表

| 模組 | 路徑 | 責任 |
|------|------|------|
| `SceneSplitter` | `backend/app/services/scene_splitter.py` | 章節切分、場景邊界偵測 |
| `FrameworkAnalyzer` | `backend/app/services/framework_analyzer.py` | 呼叫 LLM、解析輸出、驗證 schema |
| `RetrievalRouter` | `backend/app/services/retrieval_router.py` | 雙路查詢編排、結果合併 |
| `RAGFlowAdapter` | `services/vector_store/ragflow_adapter.py` | RAGFlow HTTP API 封裝 |
| `AbstractLLMClient` | `services/llm/base.py` | LLM 介面抽象 |
| `SceneFrameworkCard` | `backend/app/models/scene_framework_card.py` | Pydantic schema + SQLAlchemy ORM |

## 錯誤處理策略

| 錯誤類型 | 處理方式 |
|---------|---------|
| LLM 輸出無效 JSON | retry 最多 3 次，逐次提高 temperature |
| 缺少 evidence_quotes | `InsufficientEvidenceError`，不接受部分結果 |
| confidence < 0.3 | 記 warning，仍儲存但標記 `needs_review=True` |
| RAGFlow 連線失敗 | 降級：只用 PostgreSQL 場景卡，記 warning |
| PostgreSQL 查詢超時 | 10 秒 timeout，返回空結果不阻塞聊天 |

## Retry 策略

```
分析器 retry：
  attempt 1 → temperature=0.1
  attempt 2 → temperature=0.2，加提示「請確保有效 JSON」
  attempt 3 → temperature=0.3，加提示「請確保有 evidence_quotes」
  失敗 → AnalysisError

HTTP retry（httpx）：
  RAGFlow / Dify API：指數退避，最多 3 次
  超時：30 秒
```

## 儲存層設計

```
PostgreSQL
├── books                  書籍主表
├── chapters               章節表
├── scenes                 場景表（含原文範圍）
├── scene_framework_cards  分析卡（JSONB + 冗餘索引欄位）
├── characters             角色表
├── character_aliases      角色別名表
├── events                 事件表
├── foreshadowing_items    伏筆表
└── discussion_logs        用戶討論紀錄

RAGFlow Dataset
└── novel_chunks           scene 級別的向量 chunks
                           metadata: book_id, chapter, scene_id,
                                     focal_characters, match_level
```

## MVP → 可靠版 → 產品版 路線圖

### Phase 1: MVP（可跑通）
- [ ] txt 匯入 + regex 切章
- [ ] 簡單場景切分（段落邊界）
- [ ] Mock LLM 分析器
- [ ] 場景卡存 PostgreSQL
- [ ] 基礎 FastAPI CRUD

### Phase 2: 可靠版（真實分析）
- [ ] RAGFlow 整合入庫
- [ ] OpenAI / Anthropic 真實 LLM 分析
- [ ] 雙路查詢 + rerank
- [ ] 基礎對話 API

### Phase 3: 產品版
- [ ] Dify workflow 編排
- [ ] 批次分析進度追蹤
- [ ] 人工審閱介面
- [ ] 伏筆與角色弧線追蹤
- [ ] 跨場景關聯分析

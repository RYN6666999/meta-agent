# meta-agent

## 專案目標
零幻覺 AI Agent 系統 — 知識圖譜 + RAG + 多角色協作架構

## 工作目錄
`/Users/ryan/meta-agent/`

## 目錄結構
```
meta-agent/
├── memory/          # AI 記憶庫（跨對話持久化）
├── error-log/       # 錯誤庫（防止重蹈覆轍）
├── tech-stack/      # 技術棧鎖定文件（防幻覺）
└── truth-source/    # 驗證通過的決策記錄
```

## 🚨 每次對話啟動必做（防幻覺第一道防線）
0. 讀 `./memory/handoff/latest-handoff.md` — 上次中斷在哪？有未完成任務？
1. 讀取 `./law.json` — 載入硬規則法典（路徑/技術棧/禁止動作）
2. 查 `error-log/` — 這個問題之前踩過坑嗎？
3. 查 `tech-stack/` — 技術選型是否已鎖定？
4. 查文件優先用 qmd / Brave，不依賴模型本身知識
5. 交叉驗證後才執行

## 搜尋工具決策樹（降低成本）
- 技術文件查詢 → **qmd**（免費，結構化）
- 最新版本/API確認 → **Brave Search**（便宜）
- 網頁爬取 → **lightpanda**（免費）
- 記憶萃取/格式化 → **Groq**（免費額度高）
- 複雜推理/最終決策 → **Claude Sonnet**（最後手段）

## 決策三問
- law.json 的 forbidden 有沒有命中？
- error-log 有沒有相同根因？
- 技術棧有沒有鎖定選型？

## 已確認技術棧
- 串連層：n8n（Docker，已架好）
- RAG + 知識庫：Dify Cloud + LightRAG（port 9621，已運行）
- 知識圖譜：LightRAG + PostgreSQL（已建置，已 ingest 8 份歷史文件）
- 記憶庫：此目錄 + Git 版本控制
- 人類介面：Obsidian（iCloud 庫）
- LLM：Claude API / Gemini API（不跑本地模型）

## 環境
- 平台：macOS，8GB RAM
- 本地可跑：n8n Docker、輕量服務
- 雲端外包：Dify Cloud、n8n Cloud（備用）

## 參考路徑
- Obsidian vault: `~/Library/Mobile Documents/com~apple~CloudDocs/` 下（iCloud）
- n8n: Docker 本地架設
- 錯誤庫: `./error-log/`
- 技術棧文件: `./tech-stack/`
- 迭代紀錄文件：/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/TikTok_Notes/零幻覺迭代元代理模組meta-agent計畫.md
- 初始設定：/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/元agent.md
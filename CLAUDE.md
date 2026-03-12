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

## 決策規則（每次作決策前必讀）
1. 先查 `error-log/` — 這個問題之前踩過坑嗎？
2. 先查 `tech-stack/` — 技術選型是否已鎖定？
3. 查官方文件或 GitHub README，不依賴模型本身的知識
4. 交叉驗證後才執行

## 已確認技術棧
- 串連層：n8n（Docker，已架好）
- RAG + 知識庫：Dify.ai Cloud
- 知識圖譜：LightRAG（待建）
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

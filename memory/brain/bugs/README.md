# bugs/ — 已知問題知識庫

## 放什麼
系統/服務的已知問題：根因、修法、症狀、頻率。

## 不放什麼
- 操作手冊 → ops/
- 技術選型 → decisions/
- 規則禁令 → rules/

## 文件格式（每個服務一個文件）

```markdown
# {service} 已知問題

## ✅ 目前最佳已知事實（每次事件後更新此區塊）
- root_cause: ...
- 症狀: ...
- 修法: ...
- 驗收: ...

---
## 📅 事件時間線（只 append，不修改）
- YYYY-MM-DD: 事件描述
```

## 現有文件
- mobile-bridge.md — Mobile Bridge API / tunnel 問題
- n8n.md — n8n workflow 已知問題
- lightrag.md — LightRAG 知識圖譜問題

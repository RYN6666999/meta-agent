---
project: crm-memory-mvp
batch: X   ← 改這裡
date: YYYY-MM-DD
status: done | blocked | partial
next_batch: X+1
---

# Batch X 交接文件

## 完成了什麼
- [ ] Task X1：...
- [ ] Task X2：...

## 未完成 / 跳過（附原因）
- 無

## 已知問題
- 無

## 下一個 Batch 的人必須知道
1. ...
2. ...

## 驗收指令
```bash
# 手動驗收步驟
curl https://fdd-crm.pages.dev/api/memories
# 或具體說明要驗什麼
```

## 相關 commit
```
git log --oneline -5 tools/crm/
```

## 下一個 Batch 入口
讀 plan.md → 找到 Batch X+1 → 開始 Task 1

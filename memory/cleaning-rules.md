---
date: 2026-03-16
type: verified_truth
status: active
last_triggered: 2026-03-16
expires_after_days: 365
source: meta-agent 架構設計
---

# 記憶清洗規則

## 觸發條件
| 條件 | 動作 |
|------|------|
| 任一分類記憶數量 > 10 條 | 立即觸發清洗 |
| active 記憶超過 90 天未被 AI 引用 | 自動降為 deprecated |
| deprecated 記憶超過 30 天 | Haiku 判斷刪除或合併 |
| 同根因 error_fix 累積 > 3 條 | 合併為 1 條通用規則 |
| 每週一次定期清洗 | n8n 排程觸發 |

## 清洗流程

```
1. n8n 排程觸發（每週一 09:00）
       ↓
2. 掃描所有記憶文件的 frontmatter
   - 計算每類數量
   - 找出超過 expires_after_days 未觸發的記憶
       ↓
3. Haiku 執行清洗
   - 過期記憶：降為 deprecated
   - 同根因 error_fix：合併為新規則
   - deprecated > 30 天：刪除（先備份進 Git）
       ↓
4. 更新 law.json（forbidden / n8n_rules 同步）
       ↓
5. git commit（訊息：chore: 記憶清洗 {日期}）
       ↓
6. 寫入 memory/cleaning-log.md
```

## 記憶分類說明

| Type | 說明 | 存放位置 | 保留期限 |
|------|------|----------|----------|
| `error_fix` | 錯誤根因與修正方法 | error-log/ | 365天 |
| `tech_decision` | 技術選型決策 | tech-stack/ | 180天 |
| `verified_truth` | 驗證通過的事實 | truth-source/ | 無限期 |
| `deprecated` | 已過期記憶 | 原位置 | 30天後刪除 |

## 清洗執行者
- **模型：** claude-haiku（低成本）
- **系統提示：** 讀取 law.json + 所有 frontmatter → 輸出清洗決策 JSON
- **禁止：** Haiku 不能刪除 verified_truth，需人類確認

## 清洗日誌
位置：`memory/cleaning-log.md`
格式：
```
## 2026-03-23 清洗記錄
- 合併：error_fix × 3 → 1 條通用規則
- 降級：tech_decision/xxx.md → deprecated（90天未觸發）
- 刪除：0
- 更新 law.json：forbidden 新增 1 條
```

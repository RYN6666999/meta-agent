# 記憶系統規則

## 搜尋優先順序（黃金規則）
```
memory-mcp query → brave search → Groq → Claude Sonnet（最後手段）
```

## 記憶類型
| 類型 | 說明 |
|------|------|
| error_fix | 從 error-log 蒸餾的修正規則 |
| tech_decision | 技術選型決策（含棄用選項）|
| verified_truth | Exit 0 驗證通過的事實 |
| deprecated | 已過期，待清洗 |

## 清洗規則
- 每類記憶上限 10 條，超過 → Haiku 蒸餾合併
- active 超過 90 天未觸發 → 自動降為 deprecated
- deprecated 超過 30 天 → 刪除或合併
- 同根因 error_fix 超過 3 條 → 合併為 1 條通用規則

## 強制禁令
- 重要事實禁止只寫 error-log —— 必須雙寫到 law.json 或 brain/
- 禁止發現 bug 不立即記錄
- 禁止未窮盡工具（query_memory → brave → grep）前問用戶

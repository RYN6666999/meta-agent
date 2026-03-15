---
date: 2026-03-15
type: tech_decision
status: active
last_triggered: 2026-03-16
expires_after_days: 365
source: 零幻覺迭代元代理模組meta-agent計畫.md V1.05
---

# 技術比較：Dify 部署方式

## 結論：選 Dify Cloud

| 面向 | Dify Cloud | Dify 自架 Docker |
|------|-----------|----------------|
| RAM 需求 | 0（雲端）| 8GB（macOS VM 硬需求）|
| 部署時間 | 即用 | 數小時 |
| 費用 | 免費起步 | 吃光本地資源 |
| 控制權 | 較低 | 完整 |
| 維護 | 零 | 需自行更新 |

## 選擇理由
1. 8GB Mac 跑 Dify Docker 會吃光所有 RAM，其他服務無法運作
2. 免費層已足夠起步，無需付費
3. 最大化雲端外包，保護本地資源給 n8n + LightRAG

## 棄用：Dify 自架
Dify Cloud 達到免費上限時，優先考慮升級付費方案，
而非自架（除非遷移到 VPS）。

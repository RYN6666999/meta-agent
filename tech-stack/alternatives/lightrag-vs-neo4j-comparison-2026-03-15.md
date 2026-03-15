---
date: 2026-03-15
type: tech_decision
status: active
last_triggered: 2026-03-16
expires_after_days: 365
source: 零幻覺迭代元代理模組meta-agent計畫.md V1.05
---

# 技術比較：知識圖譜方案

## 結論：選 LightRAG + PostgreSQL

| 面向 | LightRAG + PostgreSQL | Neo4j + Qdrant |
|------|----------------------|----------------|
| RAM 需求 | ~500MB-1GB | ~4GB+ |
| 部署複雜度 | 單一 Docker | 兩個服務 |
| 向量搜尋 | 內建（pgvector）| 需獨立 Qdrant |
| 知識圖譜 | 內建 NetworkX | 完整圖資料庫 |
| 中文支援 | 良好 | 良好 |
| 成本 | 極低 | 較高 |
| 查詢語言 | REST API | Cypher |

## 選擇理由
1. 8GB Mac 資源有限，LightRAG 記憶體佔用遠低於 Neo4j
2. LightRAG 同時處理向量搜尋 + 知識圖譜，不需要兩個服務
3. 比 Microsoft GraphRAG 便宜 6000x、快 30%（EMNLP 2025 論文）

## 棄用：Neo4j + Qdrant
資源消耗太高，8GB Mac 會吃光 RAM。
未來 VPS 升級或資料量大幅增長時可重新評估。

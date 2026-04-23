# n8n 規則（蒸餾自 law.json + error-log）

## 強制規則

| # | 規則 | 原因 | 來源 |
|---|------|------|------|
| N1 | MCP 更新 workflow 後只是 draft，不自動 publish | Draft webhook = /webhook/{workflowId}/webhook/{path}，生產 webhook 需手動 publish | 2026-03-16 |
| N2 | webhook 節點名稱必須用純 ASCII | 中文名稱 → URL-encoded → 查詢時 decoded → 永不匹配 → 404 | 2026-03-16 |
| N3 | HTTP Request 動態 JSON body 用 keypair 模式 | specifyBody=json + jsonBody={{expr}} 衝突 → 靜默降級為 GET | 2026-03-16 |
| N4 | Docker 容器內呼叫 host 用 host.docker.internal | 容器內 localhost = 容器本身，不是 host | 2026-03-16 |
| N5 | Code Node 不能用 child_process | task-runner 隔離，需設 N8N_RUNNERS_ENABLED=false | 2026-03-12 |
| N6 | updateNode 用 nodeId（UUID），不能用 name | 語法：{type: updateNode, nodeId: xxx, updates: {parameters: {...}}} | 2026-03-12 |
| N7 | 禁止 Code Node 把大型二進制轉 Base64 | 19MB+ → Runner OOM 崩潰 | 2026-03-12 |

## 修復流程（publish 卡住時）
```sql
-- 查 workflow_published_version
SELECT * FROM workflow_published_version;
-- 若為空，需手動 INSERT 或 docker restart n8n
```

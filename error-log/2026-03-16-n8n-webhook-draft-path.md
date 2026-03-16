---
date: 2026-03-16
type: error_fix
status: active
last_triggered: 2026-03-16
expires_after_days: 365
topic: n8n-webhook-draft-path
---

# n8n v2.11.2 Webhook Draft 路徑問題

## 根本原因（3個連鎖 Bug）

### BUG-1：n8n API activate ≠ 生產 webhook 注冊
**現象**：`POST /api/v1/workflows/{id}/activate` 回傳 `active: true`，但 `/webhook/{path}` 仍 404。
**原因**：n8n v2.11.2 採用 draft/published 分離架構。`activate` 僅讓 workflow 進入 active 狀態，並不自動建立 **生產** webhook。`workflow_published_version` 表為空時，所有 webhook 以 draft 格式儲存。
**解法**：向 `workflow_published_version` 插入記錄後重啟 n8n。

### BUG-2：中文節點名稱導致 webhook 路徑 URL-encoding 不一致
**現象**：n8n 在 `webhook_entity` 儲存 `9ABqAtFoJWHmhkEa/webhook%20%E6%8E%A5%E6%94%B6%E5%B0%8D%E8%A9%B1/memory-extract`，但查詢時用 decoded 字串，永遠不匹配 → 404。
**原因**：SQLite 儲存的是 URL-encoded 路徑，但 Express 路由匹配時已 URL-decode。
**解法**：把 webhook 節點名稱改為純 ASCII（`Webhook 接收對話` → `Webhook`），使路徑變為 `{workflowId}/webhook/{path}`，無 encoding 問題。

### BUG-3：n8n HTTP Request 節點 specifyBody=json + jsonBody 表達式 → 發出 GET
**現象**：設定 `"method": "POST", "specifyBody": "json", "jsonBody": "={...{{ }}...}"` 後，n8n 實際發出 GET 請求。
**原因**：`jsonBody` 內嵌 `{{ JSON.stringify(...) }}` 表達式與 n8n v4.2 HTTP Request 節點的 `specifyBody: "json"` 模式衝突，body 解析失敗時靜默降級為 GET。
**解法**：改用 `specifyBody: "keypair"` + `bodyParameters.parameters[]` 逐項設定，表達式用 `={{ $json.field }}` 格式。

## 最終 Webhook URL 格式
```
Draft（目前使用）:   POST /webhook/{workflowId}/webhook/{path}
Production（待議）:  POST /webhook/{path}  ← 需要 workflow_published_version 插入
```

## 踩坑時間
約 90 分鐘（反覆試驗 DB 結構、URL encoding、HTTP 方法問題）。

## 法典更新建議
- `webhook_entity.node` 欄位必須用純 ASCII 命名
- Docker 容器內呼叫 host 服務用 `host.docker.internal` 而非 `localhost`
- HTTP Request 節點動態 body → 永遠用 `keypair` 模式

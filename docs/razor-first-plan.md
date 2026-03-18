# 剃刀優先方案：最小改動點 × 最大效果

## 核心洞見
你有 12 個 API 端點各自為政。但它們都最終進到同一個地方：`memory-mcp backend`。
**最小的改動點就在這裡**——在 backend 的最前面加一個「決策守衛」，統一檢查入口。

---

## 剃刀方案框架

### 第一步：建立 RequestContext 類（最小化）

在 `common/` 下加一個新檔 `request_context.py`，只做三件事：
```python
# common/request_context.py
from dataclasses import dataclass
from typing import Literal

@dataclass
class RequestContext:
    """統一決策入口：所有要求都要帶著這個」"""
    user_id: str              # "default" 或 "persona-xxx"
    scope: Literal["global", "persona"]  # 決策結果
    trigger_checkpoints: list[str] = None  # ["closeout", "major_guard", "kg_recovery"]
    
    def __post_init__(self):
        # 一次性判斷：user_id 決定 scope
        self.scope = "persona" if self.user_id != "default" else "global"
        self.trigger_checkpoints = self.trigger_checkpoints or []
```

**改動量**：新增 1 個檔案（13 行）

---

### 第二步：在 memory-mcp backend 最前面加守衛

目前流程：
```
api/server 
    ↓
memory-mcp.query_memory()
    ↓
LightRAG.query() 或 users/persona 本地查
```

改成：
```
api/server
    ↓ 建立 RequestContext
    ↓
memory-mcp._dispatch(context)  ← 新增守衛
    ├─ 檢查觸發點（closeout/guard/kg）
    ├─ 委派執行
    ↓
query_memory()
    ↓
LightRAG.query() 或 users/persona 本地查
```

**修改位置**：`memory-mcp/server.py` 最開頭加一個 dispatcher

```python
async def _dispatch(ctx: RequestContext, action: str, **kwargs) -> dict:
    """守衛：所有行動進來都先檢查觸發點"""
    
    # ← 狀態機會在這裡加（現在先空著）
    
    # 再委派到實際功能
    if action == "query":
        return await query_memory(kwargs['q'], kwargs.get('mode'), ctx.user_id)
    elif action == "ingest":
        return await ingest_memory(kwargs['content'], ...)
    # ...
```

**改動量**：修改 `memory-mcp/server.py`（~20 行）

---

### 第三步：改 API 端點，統一傳 context

目前：
```python
@app.post("/api/v1/query")
async def query_memory(payload: QueryRequest, ...):
    persona_id = resolve_persona_id(payload.user_id)  # 自己判
    result = await backend.query_memory(payload.q, payload.mode, persona_id)
```

改成：
```python
@app.post("/api/v1/query")
async def query_memory(payload: QueryRequest, ...):
    ctx = RequestContext(user_id=payload.user_id)  # 一次性建立
    result = await backend._dispatch(ctx, "query", q=payload.q, mode=payload.mode)
```

**改動量**：改 12 個端點（每個 2-3 行）

---

## 效果對比

| 現況 | 改後 |
|------|------|
| 12 個端點各自判 `user_id` | ctx 一次決定，貫穿整個鏈 |
| 改邏輯要改 5+ 個地方 | 改邏輯只需改 `_dispatch` 或 context 邏輯 |
| 沒有統一的決策記錄點 | RequestContext 就是決策記錄（稍後加狀態機） |
| 新功能要改 12 個端點 | 新功能在 `_dispatch` 加一個 elif |

---

## 剃刀方案總結

**改動**：
- ✅ 新增 1 個檔 `common/request_context.py`（13 行）
- ✅ 改 `memory-mcp/server.py` 加 dispatcher（20 行）
- ✅ 改 api/server 的 12 個端點（共 24-36 行）
- ✅ **總共 < 100 行改動**

**效果**：
- ✅ 統一決策入口（context 決定 scope）
- ✅ 準備狀態機（dispatcher 就是後面加狀態檢查的地方）
- ✅ 減少重複判邏輯（從 N 個地方 → 1 個地方）

**不改的**：
- ✅ memory backend 內部邏輯（query_memory / ingest_memory 各自保持）
- ✅ LightRAG   調用（維持現狀）
- ✅ 其他腳本（health_check / e2e_test 暫時不改）

---

## 下一步：狀態機整合

剃刀完成後，dispatcher 就變成了這樣：
```python
async def _dispatch(ctx: RequestContext, action: str, **kwargs):
    
    # ← [第二進度] 狀態機在這裡插入
    # 判斷 checkpoints
    # 決定「是否觸發 closeout / guard / kg_recovery」
    
    if action == "query":
        return await query_memory(...)
```

狀態機會讀取 `system-status.json`，決定「上一個 action 是否完成了 closeout / guard」。

---

## 确認清单

執行前確認：
- [ ] 同意「先改 RequestContext + dispatcher，不動 health/e2e 腳本」
- [ ] 同意「12 個端點都統一改成 `_dispatch(ctx, action, ...)`」
- [ ] 同意「state machine 在第二進度加」


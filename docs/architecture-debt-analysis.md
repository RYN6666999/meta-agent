# 架構漏洞根本原因分析

## 核心發現：MVP 快速迭代遺留的設計債務

你的系統出現「四大漏洞」不是偶然，而是慣常的 MVP 實踐模式：**邊定義、邊實現、邊修復**。結構問題跟不上需求演進才導致的。

---

## 根本原因樹

### 根因 A｜「端點優先」而非「流程優先」的架構演進

**現象**：
- 12 個 API 端點（query/ingest/loop/health/status/telegram/protocol/...）各自為政
- 每個端點都直接對接 memory backend，沒有 Facade 層統一決策

**為什麼會這樣**：
1. MVP 時期快速迭代 → 優先解決「能用」的問題，而不是「怎麼設計才對」
2. `external-brain-mvp.md` 明確說「Endpoints」列出每個端點的用途 → 設計偏向「功能堆砌」而非「流程編排」
3. Telegram webhook 與 HTTP query 各自有處理邏輯 → 沒有統一的 routing 決策點

**證據**：
```python
# api/server.py 今日有 12 個 @app route
B --> B1[api/v1/query]         # memory query
B --> B2[api/v1/ingest]        # memory write
B --> B3[api/v1/loop]          # protocol execution
B --> B4[api/v1/health/status] # status read
B --> B5[api/v1/telegram]      # TG webhook
...等等
```

**影響**：
- 改變流程時 → 要改多個端點的邏輯
- 加新规范（例如「改前必 judge」） → 找不到統一的入口點

---

### 根因 B｜沒有「強制觸發機制」—— 設計與執行脫節

**現象**：
- `bug_closeout.py` 存在，但修完 bug 沒有人自動喊「執行 closeout」
- `major_change_guard.py` 存在，但變更改完才去執行 guard
- `truth-xval` 存在，但 health/e2e 失敗時沒有統一調度誰去執行它

**為什麼會這樣**：
1. 法典（law.json）規定了規範，但沒有機制去**強制執行**
   - law.json 說「禁止 bug 修完不 log_error」→ 但沒有狀態機器去驗收這一步
   - law.json 說「health/e2e 失敗必補跑 truth-xval」→ 但各腳本自己決定要不要跑

2. 只有「規則文件」但沒有「執行檢查點」
   ```json
   // law.json
   "forbidden": [
     "禁止發現 bug 後不立即 log_error...",  // 規則
     "禁止 health/e2e 失敗後不自動觸發交叉查核..."  // 規則
   ]
   // 但誰檢查這些規則被執行了？ → 沒人
   ```

3. 每個腳本內部有 auto_recovery 判邏輯，導致分散決策
   ```python
   # health_check.py
   if failures:
       run_auto_recovery(trigger='health_check_failure', failures=failures)
   
   # e2e_test.py
   if not (ok and final_ok):
       run_auto_recovery(detail=detail)
   
   # 各自決定「何時執行修復」→ 容易遺漏
   ```

**影響**：
- 用戶要靠「記得去執行」，而不是系統自動觸發
- 遺漏率非常高（因為沒有強制檢查點）

---

### 根因 C｜狀態讀寫不統一 —— 各腳本自建一套

**現象**：
- health_check.py ← 寫 `system-status.health_check`
- e2e_test.py ← 寫 `system-status.e2e_memory_extract`
- auto_recovery 各自寫 `system-status.auto_recovery`
- 結果是 status 檔分片存放，容易不一致

**為什麼會這樣**：
1. `common/status_store.py` 設計時就是「分片模式」
   ```python
   SHARD_KEYS = {
       'api_health',
       'api_usage',
       'health_check',
       'e2e_memory_extract',
       'code_intelligence',
       'truth_xval',
       'degraded_queue',
       'auto_recovery',    # ← 分散的 shard
       ...
   }
   ```

2. 各腳本先各自全做，再決定要存到哪個 shard
   ```python
   # health_check.py
   write_health_status(...)  # 自己寫完整過程
   update_reliability_metrics(...)
   status['health_check'] = health_section
   save_status(status)
   
   # e2e_test.py
   update_e2e_status(...)  # 各自實現
   status['e2e_memory_extract'] = e2e_section
   save_status(status)
   ```

3. 長期沒有統一的 State 物件或協定 → 各腳本「各自做各自的」

**影響**：
- 修改某個檢查邏輯時，很難知道是否影響了其他 shard
- 路由層（API）讀狀態時，容易讀到不一致的快照

---

### 根因 D｜Context 隔離決策在執行層而非入口層

**現象**：
- Telegram webhook 與 HTTP query 都會調用 handle_telegram_text 或 query_memory
- 內部根據 `user_id == "default"?` 判斷 scope（全域 vs persona-local）
- 結果是每個端點重複做這個判斷

**為什麼會這樣**：
1. MVP 階段沒有統一的 Context 物件
   ```python
   # api/server.py @ query_memory endpoint
   persona_id = resolve_persona_id(payload.user_id)  # 每個端點自己做
   ...
   
   # api/server.py @ ingest_memory endpoint
   persona_id = resolve_persona_id(payload.user_id)  # 重複做一遍
   ...
   
   # memory-mcp/server.py @ query_memory_structured
   if user_id != "default":  # 再做一遍
       result, reranked = _local_only_query_result(...)
   ```

2. Context 應該由 Facade 層創建，然後貫穿所有呼叫鏈
   - 現在：每個地方都在判斷 `user_id == "default"`
   - 應該：請求進入時 → 建立 Context(scope=global|persona_local, persona_id=...) → 傳遞下去

**影響**：
- 新增一個 scope 類型（例如「team」）時，要改很多地方
- Context 切換時無清晰的檢查點

---

## 演進時間軸對照

| 時期 | 做了什麼 | 為什麼是這樣 | 遺留債務 |
|------|--------|-----------|---------|
| **Phase 0: 基礎**（之前） | 建立 memory-mcp、LightRAG、health_check | 優先「動起來」 | 各自一套邏輯 |
| **Phase 1: MVP HTTP API**（最近） | 加 api/server，12 個端點堆砌 | 優先「能用」 | 沒有統一入口層 |
| **Phase 2: 規範硬化**（最近） | law.json 寫規則，bug_closeout / major_change_guard 寫工具 | 優先「有規則」 | 規則與執行脫節 |
| **現在** | 發現漏洞：12 個端點各自為政、修復路由分散、狀態不統一 | - | **需要重構 Facade 層** |

---

## 根本原因總結表

| 漏洞 | 根本原因 | 根源決策 | 修復難度 |
|------|--------|---------|---------|
| **漏洞 1**｜決策路由無單一入口 | MVP 端點堆砌，沒有 Facade 層 | 優先快速迭代 | 高（改 12 個端點） |
| **漏洞 2**｜強制觸發機制缺失 | 規則寫檔案，沒有執行網 | 設計與執行分離 | 中（加狀態機） |
| **漏洞 3**｜狀態讀寫不統一 | 各腳本獨立寫狀態 | MVP 沒設計統一 State | 中（統一 State 物件） |
| **漏洞 4**｜Context 隔離無檢查點 | user_id 判定分散在 N 個地方 | 入口層沒做 Context 創建 | 低（創建 Context 類） |

---

## 設計反思

### 「法典寫得好不等於系統執行」

你的 law.json 和 CLAUDE.md 寫得很完善，但**最大的漏洞其實不在規則本身，而在於「誰來驗收規則被執行」**。

現在的模式：
```
規則寫入 law.json
    ↓
每次手動想起來就檢查
    ↓
常常忘記 ❌
```

應該的模式：
```
規則寫入 law.json
    ↓
強制觸發機制 → 狀態機 → 驗收
    ↓
100% 命中率 ✅
```

### 為什麼 MVP 快速迭代會遺留這些債務

1. **時間壓力**：快速推出 → 優先做「功能」而非「架構」
2. **需求演進**：一開始 API 只是「記憶查詢」，後來加了 Telegram，再後來加了 GOLEM 協議處理 → 端點越來越多
3. **沒有預警**：沒有人在 3-6 個月前說「你要加 Facade 層」
4. **技術債利息攀升**：現在改一個邏輯要改 5 個地方 → 催生了 bug


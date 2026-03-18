# 核心使命檢視 × 現有架構對標報告

## 北極星目標

| 目標 | 現狀 | 達成度 | 漏洞 |
|------|------|--------|------|
| **1. 對話中斷不失憶** | persona-local + LightRAG + memory-mcp | **70%** | ❌ 上下文切換時機制不明確；persona 切換無自動檢查點 |
| **2. Bug 修復可追溯備份** | error-log / bug_closeout.py / truth-source | **60%** | ❌ closeout pipeline 容易漏步；log_error 常忘記同步觸發 |
| **3. 重大變更不漏判** | major_change_guard.py / milestone-judge | **50%** | ❌ guard 常被繞過；變更前無強制先檢查點 |
| **4. KG 品質可持續維護** | health_check / e2e_test / truth-xval / dedup | **55%** | ❌ 失敗恢復路徑分散；無統一調度中心 |

---

## 三個硬規則路由檢視

### 路由 A｜Bug Closeout Pipeline

**使命**：修完 bug → 自動走 error-log → truth-source → git backup → xval

**現有流程**：
```
修 bug → (手動選擇) → run bug_closeout.py?
            ↓ Yes → error-log + ingest_memory + git-score
            ↓ No  → bug 忘記備份
```

**漏洞**：
1. ❌ 沒有**強制觸發機制** - 修完 bug 沒有人自動喊「執行 closeout」
2. ❌ 決策無狀態記錄 - 若中斷，下次啟動不知道上次修了哪個 bug
3. ❌ closeout 本身有分散邏輯 - `bug_closeout.py` 內部還要判斷多個選項

---

### 路由 B｜重大變更 Guard

**使命**：涉及 `api/`、`scripts/`、`law.json` 的變更 → 必先 milestone-judge + git-score

**現有流程**：
```
修改檔案 → (改完後才想起?) → run major_change_guard.py?
             ↓ Yes → milestone-judge + git-score + git commit
             ↓ No  → 變更沒有決策記錄，直接 commit
```

**漏洞**：
1. ❌ 沒有**提前檢查點** - 改完才判斷太晚，應該改前判定是否 high-risk
2. ❌ 無法追溯決策 - 往往改了後發現「哦，忘了執行 guard」
3. ❌ 難以執行規範 - 用戶容易 hardcode 改變而忽略 guard

---

### 路由 C｜KG 維護迴圈

**使命**：health/e2e 失敗 → 自動觸發 truth-xval → dedup → 自我修復

**現有流程**：
```
health_check 失敗 → write_health_status()
                    ↓ (if 失敗)
                    └→ run_auto_recovery() 
                         ├─ truth-xval
                         └─ dedup-lightrag --dry-run

e2e_test 失敗 → write_e2e_status()
            ↓ (if 失敗)
            └→ run_auto_recovery()
                 ├─ truth-xval
                 ├─ reactivate_webhooks
                 └─ dedup-lightrag --dry-run
```

**漏洞**：
1. ❌ 修復邏輯分散在兩個腳本 - `health_check.py` 和 `e2e_test.py` 各自寫一套
2. ❌ 回圈條件模糊 - `dry-run` 只預演，沒有「執行恢復」的真實步驟
3. ❌ 無統一調度中心 - 各腳本內自行決定「是否 run_auto_recovery」，容易遺漏

---

## 架構層級的漏洞

| 漏洞 | 位置 | 影響 | 建議 |
|------|------|------|------|
| **漏洞 1**｜決策路由無單一入口 | api/server 有 12 個端點 | 複雜度高，容易繞過規範 | 改成 3 個統一端點（query/ingest/execute） |
| **漏洞 2**｜狀態結構不統一 | status_store 分片存放，每個腳本自己寫 | 狀態讀寫容易不一致 | 定義統一的 State 物件（health\|e2e\|context） |
| **漏洞 3**｜修復觸發無中樞 | health/e2e/smoke 各自調用 run_auto_recovery | 邏輯分散難維保 | 建立 Recovery Orchestrator（集中調度） |
| **漏洞 4**｜context 隔離有漏洞 | user_id 判定在執行層而非入口層 | 容易混淆 persona 範圍 | 在 Facade 層就決定 scope，傳 context 物件 |

---

## 改進優先序

### P0｜建立三大強制路由的中樞調度
- **目標**：無論是 bug/重大變更/KG 失敗，都有統一的執行驗收點
- **依賴**：統一狀態結構 + 統一決策入口
- **成果**：closeout/guard/kg 命中率達 100%

### P1｜API 層簡化 + 統一決策入口
- **目標**：12 端點 → 3 端點，所有邏輯統一走 Facade layer
- **依件**：無
- **成果**：架構複雜度 ÷ 3

### P2｜狀態結構統一化
- **目標**：所有 health/e2e/context 狀態寫入統一格式（不再各自分片）
- **依賴**：P0 + P1
- **成果**：狀態讀寫一致，追蹤更清晰

---

## 自查清單

**核心使命達成度**：
- ✅ 對話連續性（persona-local + global memory）存在
- ⚠️ Bug 可追溯（yes，但 closeout 常漏步）
- ⚠️ 重大變更防護（yes，但 guard 容易被繞過）
- ⚠️ KG 維護機制（yes，但無統一調度，故障恢復常不完整）

**核心缺陷**：
1. 無強制流程觸發機制（修完 bug/變更後無人自動喊「執行校驗」）
2. 決策邏輯分散（每個腳本自己判斷「我該執行修復嗎」）
3. 狀態讀寫不統一（各腳本自行存狀態，容易衝突）
4. 上下文切換無檢查點（persona 切換、session 中斷無明確銜接機制）


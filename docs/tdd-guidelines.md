
# Zero-Trust 專案專屬 TDD（測試驅動開發）規範

## 一、總則
- 所有架構層（Control/Data/Verify/Execute/Knowledge/Observer）與閉環流程，皆須以 TDD 為落地基礎。
- 測試必須驗證：功能正確性、資料一致性、權限/風險分級、異常處理、追溯鏈、閉環行為（如自動恢復、知識沉澱）。
- 測試必須可自動化、可重現、可產生機器可讀報告，並能追溯到需求、設計、知識文件與決策紀錄。

## 二、各階段/模組 TDD 要求

### 1. Control Plane（規則、風險分級、決策記錄）
- 規則引擎（policy engine）每條 rule 必須有：
  - 通過/不通過（pass/block）測試
  - 風險分級正確性測試（P0/P1/P2）
  - 禁區、例外、白名單測試
- 決策記錄必須驗證 decision_id、來源鏈、rule hit 可追溯

### 2. Data Plane（狀態 shards、事件文檔、lineage）
- 狀態提交/同步必須有：
  - 原子性測試（不可寫一半）
  - 多份狀態一致性測試（MSS）
  - 異常 rollback 測試
- 事件文檔、lineage 必須驗證 metadata 完整性、可追溯性

### 3. Verify Plane（MSS、truth-xval、驗證）
- MSS 驗證必須有：
  - 三份狀態不同步時能正確偵測與標記
  - 修復後自動驗證同步一致
- truth-xval 必須有：
  - 多來源交叉驗證 pass/fail 測試
  - 驗證失敗時自動進入 closeout 流程

### 4. Execute Plane（原子 action、checkpoint、auto-recovery）
- 原子 action 必須有：
  - 單一任務執行正確性
  - 執行失敗時自動重試、退避、降級測試
- checkpoint registry 必須驗證流程註冊、執行順序、異常處理

### 5. Knowledge/Observer Plane（知識沉澱、監控、週報）
- 每次 closeout 必須有：
  - 知識文件自動產生測試（error_fix/decision）
  - metadata、lineage、owner、deadline 完整性測試
- 週報產生、KPI 更新必須有自動化測試

### 6. 閉環/PDCA 流程
- 每個失敗事件必須有：
  - 修復→驗證→知識沉澱→回灌全流程測試
  - 人工介入後二次驗證測試
  - CAPA/Systemic Incident 結案前驗證與知識沉澱測試

## 三、範例（針對本專案 domain）
```python
# Control Plane: 風險分級測試
def test_policy_engine_risk_gate():
    result = policy_engine.evaluate(input_data)
    assert result['risk_level'] in ['P0', 'P1', 'P2']
    assert result['blocked'] is True or result['blocked'] is False

# Data Plane: 狀態同步一致性
def test_status_shard_consistency():
    update_all_shards(new_state)
    assert check_mss_sync() is True

# Verify Plane: 多來源交叉驗證
def test_truth_xval_six_angle():
    result = six_angle_verifier.verify(facts)
    assert result['all_green'] or result['blocked']

# Execute Plane: 自動恢復閉環
def test_auto_recovery_loop():
    fail_action()
    assert auto_recovery_triggered()
    assert closeout_written()

# Knowledge Plane: 知識文件產生
def test_knowledge_doc_generation():
    closeout_event()
    doc = get_latest_knowledge_doc()
    assert doc['metadata']['owner']
    assert doc['metadata']['lineage']
```

## 四、驗證標準
- 各層/流程 100% 關鍵路徑必測，覆蓋率不得低於 95%
- 測試必須自動化執行於 CI pipeline，產生 coverage 與追溯報告
- 每個測試案例需標註對應需求、決策、知識文件 ID
- 失敗閉環：每次失敗必須有對應修復測試與知識沉澱驗證

## 五、常見反模式（嚴禁）
- 只測 happy path，未覆蓋異常/權限/資料一致性/閉環
- 測試與需求、知識文件、決策紀錄脫鉤，無法追溯
- 測試僅手動執行，未自動化
- 重構後未全數通過測試即提交
- 測試覆蓋率低於標準仍允許合併

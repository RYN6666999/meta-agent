# Novel Analyzer — 修訂優化計劃 v2
## 框架：SDD → BDD → TDD 三層驗證策略

---

## 0. 問題清單（來源：截圖回報 + 代碼稽核）

| ID | 類型 | 描述 | 嚴重度 |
|----|------|------|--------|
| B1 | Bug | 談判場景篩選角色後空白 | P0 |
| B2 | Bug | 場景 Modal 在「全部書籍」模式被攔截，無法點擊 | P0 |
| B3 | Bug | `situation` 欄位在場景卡片顯示為角色名（API 快取/server 啟動問題） | P1 |
| B4 | Bug | 行動決策頁描述「寧凡面臨關鍵抉擇」hardcoded | P1 |
| F1 | Feature | 角色弧線頁改下拉選單（現為 text input） | P1 |
| F2 | Feature | 簡體 → 繁體自動轉換（上傳時觸發） | P2 |

---

## 一、SDD：系統設計規格（OpenAPI 合約片段）

### 1.1 修訂的 API Contract

```yaml
# =============================================
# /api/negotiation — 談判場景查詢
# =============================================
paths:
  /api/negotiation:
    get:
      summary: 查詢談判場景
      parameters:
        - name: book_id
          in: query
          required: false
          schema: { type: string }
          description: 限定書籍；不傳 = 全書查詢
        - name: focal_character
          in: query
          required: false
          schema: { type: string }
          description: 過濾主角；URL encode 必須正確（繁體）
      responses:
        "200":
          description: 談判場景列表
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/NegotiationScene"

  # =============================================
  # /api/characters — 角色清單（支援 book scope）
  # =============================================
  /api/characters:
    get:
      summary: 取得角色清單（用於下拉選單）
      parameters:
        - name: book_id
          in: query
          required: false
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  characters:
                    type: array
                    items: { type: string }
                example:
                  characters: ["寧凡", "輝子", "喬菲"]

  # =============================================
  # /api/scene/{chapter}/{scene} — 場景詳情
  # =============================================
  /api/scene/{chapter}/{scene}:
    get:
      summary: 場景詳情（用於 Modal）
      parameters:
        - name: chapter
          in: path
          required: true
          schema: { type: integer }
        - name: scene
          in: path
          required: true
          schema: { type: integer }
        - name: book_id
          in: query
          required: false        # ← 全部書籍模式下應為 optional
          schema: { type: string }
      responses:
        "200":
          description: 完整場景卡
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/SceneDetail"
        "404": { description: 場景不存在 }

  # =============================================
  # /api/arc/{character} — 角色弧線
  # =============================================
  /api/arc/{character}:
    get:
      summary: 角色弧線資料
      parameters:
        - name: character
          in: path
          required: true
          schema: { type: string }
          description: 角色名（URL encoded 繁體）
        - name: book_id
          in: query
          required: false
          schema: { type: string }
      responses:
        "200":
          description: 弧線點陣列
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/ArcPoint"

components:
  schemas:
    NegotiationScene:
      type: object
      required: [chapter_number, scene_number, focal_character, is_negotiation_scene]
      properties:
        chapter_number:   { type: integer }
        scene_number:     { type: integer }
        focal_character:  { type: string }
        confidence_score: { type: number, minimum: 0, maximum: 1 }
        match_level:      { type: string, enum: [complete, partial, weak] }
        negotiation_pattern_tags: { type: array, items: { type: string } }
        situation:
          type: object
          description: JSON 反序列化後的局勢描述
        scene_text_preview: { type: string, maxLength: 300 }

    SceneDetail:
      type: object
      required: [chapter_number, scene_number, book_id]
      properties:
        situation:  { type: object }
        desire:     { type: object }
        mind_shift: { type: object }
        judgment:   { type: object }
        focal_character: { type: string }

    ArcPoint:
      type: object
      required: [chapter_number, scene_number, mind_shift_type, shift_score]
      properties:
        chapter_number:     { type: integer }
        scene_number:       { type: integer }
        mind_shift_type:
          type: string
          enum: [none, emotion, stance, strategy, values, identity]
        mind_shift_intensity: { type: integer, minimum: 1, maximum: 5 }
        shift_score:          { type: integer, minimum: 0, maximum: 5 }
        is_negotiation_scene: { type: boolean }
```

### 1.2 前端狀態機設計（解決 Bug B1/B2 的根因）

```
_dataScope = 'book' | 'all'
_currentBookId = string | null

URL 組合規則（Function: apiUrl(path)）：
  if path 已含 '?' → append '&book_id=...'
  else             → append '?book_id=...'
  if _dataScope = 'all' → 不添加 book_id（全書查詢）

Modal 開啟規則（Function: openSceneModal）：
  舊規則: requiresSelectedBook() → 彈 alert 阻斷  ← BUG
  新規則: book_id 為 optional，以 chapter+scene 唯一查詢
         若多書有重疊 id → 補 book_id 做精確查詢
```

---

## 二、BDD：行為驅動規格

### Feature B1：談判場景角色篩選

```gherkin
Feature: 談判場景依角色篩選

  Background:
    Given 系統已載入書籍「上城之下」（shangchengzhixia-001）
    And DB 中有 56 筆 focal_character='寧凡' 的談判場景

  Scenario: 選擇角色後顯示場景
    Given 使用者在「談判場景」頁面
    And 書籍 scope = 'book', 已選取「上城之下」
    When 使用者從角色下拉選單選擇「寧凡」
    Then 頁面顯示 56 筆場景
    And 每筆卡片顯示 focal_character = 寧凡

  Scenario: 全部書籍模式下選擇角色
    Given scope = 'all'（未選書籍）
    When 使用者選擇角色「寧凡」
    Then API 呼叫 /api/negotiation?focal_character=寧凡（不加 book_id）
    And 頁面顯示跨書籍的所有寧凡談判場景

  Scenario: 角色下拉選單初始化
    Given 使用者進入談判場景頁
    When 頁面載入完成
    Then 下拉選單列出書籍下所有 distinct focal_character
    And 預設值為「全部角色」（空字串，不過濾）
```

### Feature B2：場景 Modal 可點擊（全模式）

```gherkin
Feature: 場景詳情 Modal 全範圍可開啟

  Scenario: book 模式點擊場景卡
    Given scope = 'book', 已選「上城之下」
    When 使用者點擊任一場景卡片
    Then Modal 開啟，顯示該場景的局心欲變詳情

  Scenario: all 模式點擊場景卡（修復 B2）
    Given scope = 'all'（未選書籍）
    When 使用者在場景列表點擊某卡片
    Then Modal 呼叫 /api/scene/{ch}/{sc}（不帶 book_id）
    And 若查詢結果唯一 → 正常顯示
    And 若結果多筆 → 顯示書籍選擇提示

  Scenario: 從 Dashboard Top5 點擊
    Given 使用者在 Dashboard
    When 點擊「高價值談判場景 Top5」的卡片
    Then 跳轉或開啟 Modal 顯示該場景詳情
```

### Feature F1：角色弧線下拉選單

```gherkin
Feature: 角色弧線頁使用下拉選單

  Scenario: 進入角色弧線頁自動載入
    Given 使用者點擊「角色弧線」頁籤
    When 頁面切換完成
    Then 下拉選單自動呼叫 /api/characters 填充選項
    And 自動選取清單第一個角色
    And 弧線圖自動渲染（不需手動輸入）

  Scenario: 切換角色
    Given 弧線頁已顯示寧凡的弧線
    When 使用者從下拉選單切換到「輝子」
    Then 呼叫 /api/arc/輝子
    And 圖表更新為輝子的心態轉變曲線

  Scenario: 書籍 scope 切換
    Given 使用者在 scope='book', 選了「上城之下」
    When 切換到弧線頁
    Then 下拉選單只顯示上城之下的角色
    And 呼叫 /api/arc/{char}?book_id=shangchengzhixia-001
```

### Feature F2：簡繁自動轉換

```gherkin
Feature: 上傳簡體文本自動轉繁體

  Scenario: 偵測並轉換簡體文件
    Given 使用者上傳「引爆点.txt」（簡體）
    When 後端 /api/upload 接收檔案
    Then 偵測文字為簡體（繁體比例 < 20%）
    And 呼叫 opencc 轉換為繁體台灣（t2tw）
    And 轉換後文字存入 DB 的 scene_text 欄位
    And Response 含 { "converted": true, "encoding": "zh-TW" }

  Scenario: 繁體文件不轉換
    Given 使用者上傳「上城之下.txt」（繁體）
    When 後端接收檔案
    Then 偵測為繁體（繁體比例 > 80%）
    And 不執行轉換，直接儲存
    And Response 含 { "converted": false }
```

---

## 三、TDD：驗證策略與閘門

### 3.1 驗證層次（由外而內）

```
Layer 1: API Smoke Test（curl）
  → 驗證 HTTP 狀態碼 + response schema
  → 工具：curl + python3 -c "json.loads..."

Layer 2: DB Assertion（SQLite）
  → 驗證資料完整性與欄位型別
  → 工具：sqlite3 CLI + python3

Layer 3: Frontend Logic（Console）
  → 驗證 JS 函數邏輯與 URL 組合
  → 工具：Chrome DevTools console
```

### 3.2 每個 Bug/Feature 的確認腳本

#### B1 驗證：談判場景篩選
```bash
# API 層（已知正常）
curl -s 'http://localhost:8765/api/negotiation?focal_character=%E5%AF%A7%E5%87%A1&book_id=shangchengzhixia-001' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); assert len(d)==56, f'FAIL: got {len(d)}'; print('PASS: 56 scenes')"

# 前端層：在 browser console 執行
# window._dataScope = 'book'; window._currentBookId = 'shangchengzhixia-001';
# document.getElementById('negoCharFilter').value = '寧凡'; loadNegotiation();
# 預期：列表顯示 56 筆，非空白
```

#### B2 驗證：Modal 全模式可點
```bash
# 確認 /api/scene 不帶 book_id 可正常回傳
curl -s 'http://localhost:8765/api/scene/1/1' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'focal_character' in d; print('PASS')"
```

#### B3 驗證：situation 欄位
```bash
curl -s 'http://localhost:8765/api/scenes?limit=1&book_id=shangchengzhixia-001' \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
item = d['items'][0]
assert 'situation' in item, 'FAIL: no situation field'
assert item['situation'] is not None, 'FAIL: situation is null'
print('PASS: situation =', str(item['situation'])[:80])
"
```

#### F1 驗證：角色清單 API
```bash
curl -s 'http://localhost:8765/api/characters?book_id=shangchengzhixia-001' \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
chars = d['characters']
assert len(chars) > 0, 'FAIL: empty characters'
assert '寧凡' in chars, f'FAIL: 寧凡 not in {chars[:5]}'
print(f'PASS: {len(chars)} characters, includes 寧凡')
"
```

#### F2 驗證：簡繁轉換
```bash
python3 -c "
import opencc
c = opencc.OpenCC('s2twp')
test = '联系员在这里'
result = c.convert(test)
assert '聯繫' in result or '聯絡' in result, f'FAIL: {result}'
print(f'PASS: {test} → {result}')
"
```

### 3.3 Definition of Done（DoD）

每個 Bug/Feature 完成的判斷標準：

| ID | 完成條件 |
|----|---------|
| B1 | ① API curl 回傳 56 筆 ② 瀏覽器篩選後顯示正確數量 ③ 空角色不篩選（顯示全部） |
| B2 | ① all 模式點擊卡片不彈 alert ② modal 正確顯示場景詳情 ③ book 模式不受影響 |
| B3 | ① curl /api/scenes 回傳含 `situation` 非 null ② 場景卡片顯示 `external_situation` 文字 |
| B4 | ① 行動決策頁描述不含角色名 ② 切換書籍後描述不變動 |
| F1 | ① 進入弧線頁自動顯示下拉選單 ② 切換角色圖表更新 ③ 無需手動輸入 |
| F2 | ① 上傳簡體文件後 DB 存繁體 ② API response 含 converted 欄位 ③ 繁體文件不觸發轉換 |

---

## 四、執行優先序與分工

### Sprint 1（立即修復 — P0 Bugs）

```
Task 1: B1 談判篩選 Bug
  修改位置: frontend/index.html → loadNegotiation() + loadNegotiationCharacters()
  策略: 移除 requiresSelectedBook() 攔截，改為 scope-aware URL 組合
  驗證: B1 DoD ①②③

Task 2: B2 Modal 全模式
  修改位置: frontend/index.html → openSceneModal()
  策略: book_id 改為 optional 參數，不帶 book_id 時只帶 ch+scene
  驗證: B2 DoD ①②③
```

### Sprint 2（UX 改進 — P1）

```
Task 3: B3 situation 欄位確認
  修改位置: server 重啟確認 + frontend scene card 模板
  驗證: B3 DoD ①②

Task 4: B4 行動決策描述
  修改位置: frontend/index.html → 決策頁描述段落
  策略: 改為通用描述，不引用角色名

Task 5: F1 角色弧線下拉選單
  修改位置: frontend/index.html → arc-controls HTML + loadArcCharacters() + loadArc()
  策略: <input> → <select>，進頁面自動呼叫 /api/characters 填充 + 自動載入第一個角色
  驗證: F1 DoD ①②③
```

### Sprint 3（新功能 — P2）

```
Task 6: F2 簡繁轉換
  修改位置: server.py → api_upload() + 新建 services/s2t.py
  依賴: pip3 install opencc-python-reimplemented
  驗證: F2 DoD ①②③
```

---

## 五、風險與邊界條件

| 風險 | 描述 | 緩解方案 |
|------|------|---------|
| ch+scene 跨書重疊 | 多書可能有相同 ch1/s1 | openSceneModal 補傳 book_id（由 data-book-id 屬性） |
| opencc 安裝失敗 | 系統 python3 無 pip 寫入權限 | 改用 pip3 install --user 或 homebrew |
| 角色清單含垃圾名 | DB 有 focal_character='法則' 等垃圾值 | /api/characters 加 WHERE LEN(focal_character) > 1 AND focal_character NOT LIKE '%未明確%' |
| situation 為 null | 舊資料未有 situation 欄位 | 前端 fallback：priority → situation.external_situation → scene_text_preview |

---

## 六、快速驗證入口

```bash
# 一鍵跑所有 smoke tests
python3 scripts/smoke_test.py
```

（此腳本待 Sprint 1 完成後建立，包含所有 B1-F2 的 curl 驗證邏輯）

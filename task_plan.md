# Task Plan：記憶清洗 + Git 技術分岔

**目標：** 為 meta-agent 加入記憶清洗分類機制與 Git 技術決策備份系統
**建立時間：** 2026-03-16
**狀態：** in_progress

---

## 任務拆分

### Task A：記憶清洗分類規則系統
**目的：** 讓每條記憶有生命週期，防止舊資訊污染 AI 決策

#### A1：設計 Frontmatter 規範 `[x]`
- 定義 memory type 分類（error_fix / tech_decision / verified_truth / deprecated）
- 定義欄位：date / type / status / last_triggered / expires_after_days
- 寫入 law.json 的 memory_rules 區塊

#### A2：補全現有記憶文件的 Frontmatter `[x]`
- error-log/ 下的檔案補上分類
- tech-stack/ 下的檔案補上分類
- truth-source/ 下的檔案補上分類（目前是否為空？）

#### A3：建立清洗規則文件 `[x]`
- 位置：`/Users/ryan/meta-agent/memory/cleaning-rules.md`
- 內容：觸發條件、清洗流程、由誰執行（Haiku）

#### A4：更新 law.json 加入 memory_rules `[x]`
- 每類上限 10 條
- 90天未觸發 → deprecated
- deprecated 30天 → Haiku 判斷刪除/合併

---

### Task B：Git 技術決策分岔備份
**目的：** 保存每次重大技術選擇的完整討論，可考古、可對比

#### B1：建立 Git branching 規範 `[x]`
- 寫入 law.json 的 git_rules 區塊
- 命名格式：`decision/{topic}-{YYYY-MM-DD}`

#### B2：建立已有決策的 branch `[x]`
- `decision/lightrag-vs-neo4j-2026-03-15`
- `decision/dify-cloud-vs-selfhost-2026-03-15`
- `decision/v2-simplify-2026-03-15`

#### B3：建立 tech-stack/alternatives/ 目錄 `[x]`
- 存放每次技術比較的原始文件
- 命名：`{topic}-comparison.md`

#### B4：建立標準決策記錄模板 `[x]`
- 位置：`/Users/ryan/meta-agent/truth-source/decision-template.md`
- 內容：選項A vs B、決策理由、棄用原因、日期

---

## 執行順序
1. A1 → A4（更新 law.json）
2. A2（補現有文件）
3. A3（清洗規則文件）
4. B1（更新 law.json）
5. B3（建目錄 + 比較文件）
6. B4（決策模板）
7. B2（建 decision branches）
8. git commit all

---

## 關鍵檔案
- `/Users/ryan/meta-agent/law.json` — 加入 memory_rules + git_rules
- `/Users/ryan/meta-agent/memory/cleaning-rules.md` — 新建
- `/Users/ryan/meta-agent/tech-stack/alternatives/` — 新建目錄
- `/Users/ryan/meta-agent/truth-source/decision-template.md` — 新建

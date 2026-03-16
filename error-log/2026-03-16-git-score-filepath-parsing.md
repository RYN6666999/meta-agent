---
date: 2026-03-16
type: error_fix
status: active
last_triggered: 2026-03-16
expires_after_days: 365
topic: git-score-filepath-parsing
---

# Error: T1+T2 驗證測試：git-score.py filepath 解析 bug（line[3:].strip() 截掉首

## 根本原因
T1+T2 驗證測試：git-score.py filepath 解析 bug（line[3:].strip() 截掉首字元）導致 CLAUDE.md → LAUDE.md，memory/ → emory/，檔案評分嚴重偏低

## 解決方案
改用 re.match(r'^(.{2}) (.+)', line) 取 group(2) 作為 filepath，確保兩位狀態碼後的完整路徑被正確解析

## 背景
milestone-judge.py 同步套用相同修正。此錯誤導致分支評分系統長期失效，提交頻率異常低。

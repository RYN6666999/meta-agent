# genapark MCP 伺服器專案

本專案為 Model Context Protocol (MCP) 伺服器範本，適用於 macOS，並可與 meta-agent 專案協作。

## 結構
- genapark/
  - app/
  - scripts/
  - tests/
  - requirements.txt
  - main.py
  - README.md

## 啟動方式
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 說明
- app/: 主要業務邏輯
- scripts/: 工具與啟動腳本
- tests/: 測試程式
- requirements.txt: 依賴
- main.py: 入口

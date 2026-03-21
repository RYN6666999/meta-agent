# tools/

此目錄存放 meta-agent 生態系中的**獨立工具**，每個子資料夾是一個可獨立運行的應用或服務。

## 工具清單

| 資料夾 | 定位 | 啟動方式 | Port |
|--------|------|----------|------|
| `crm/` | CRM 人脈樹管理系統（單頁 SPA） | `python3 -m http.server 8080 --directory tools/crm` | 8080 |
| `memory-mcp/` | Memory MCP Server（本地記憶查詢） | `python3 tools/memory-mcp/server.py` | — |

## 開發規範

- 每個工具**自給自足**，不依賴同層其他工具
- 共用邏輯放 `../common/`
- 對外服務 Port 記錄在 `.claude/launch.json`

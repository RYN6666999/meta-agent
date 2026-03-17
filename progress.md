## 2026-03-17
- 啟動 D10（驗證機制穩定化）規劃，主軸由擴功能轉為穩定驗證鏈路。
- 執行即時基線檢查：`scripts/health_check.py`、`scripts/e2e_test.py`。
- 基線結果：LightRAG timeout、memory-extract HTTP 500（SQLITE_CORRUPT），n8n/Groq 正常。
- 狀態檔已更新：`memory/system-status.json`（health/e2e 最新失敗時間與細節）。
- 任務計劃檔更新為 D10：`task_plan.md`（含場景目標、SLO、分階段驗證與回滾）。
- 研究 lightpanda 對標方案，完成完整評估分析（→ 存入 `memory/lightpanda-decision-analysis-2026-03-17.md`）。
- 決策：暫時不追 Lightpanda，改先實施方案 C（JSON-LD fallback 層）。
- **實施 P2-D：Instagram 提取品質改善** — JSON-LD fallback
  - 新增 `_run_jsonld()` 函數，從 IG 頁面爬取 JSON-LD schema + og: meta tags
  - 集成到 fallback 鏈：yt-dlp → [新] JSON-LD → instaloader
  - 觸發條件：yt-dlp 返回 0 媒體但有 caption 時自動觸發
  - Unit test 驗證：✅ 10/10 passed (parsing + fallback chain logic)
- 環境：在虛擬環境安裝 instaloader
- 建立 smoke test 腳本（`scripts/test_jsonld_fallback.py`）與單元測試（`scripts/test_jsonld_unit.py`）
- 記錄完整實施報告：`truth-source/2026-03-17-jsonld-fallback-implementation.md`
- master-plan 更新 P2-D 狀態為「進行中」，預期 1 週後重評效果

# Progress Log

## 2026-03-16
- 建立 D3 方向：商業級落差分析 + 外掛大腦 MVP 規格 + 第一版介面層實作。
- 完成 git/history 與 repo 架構分析，確認目前缺的是 HTTP 對外介面，而不是記憶核心本身。
- 建立規劃檔：`task_plan.md`、`findings.md`、`progress.md`。
- 完成 `api/server.py` 與 `scripts/test_api.py`。
- 以 `.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 9901` 啟動 API。
- smoke test 通過：`health` / `rules` / `query` / `trace` 皆為 HTTP 200。
- `memory/system-status.json` 已新增 `api_health`，外掛大腦 MVP 已可本機使用。

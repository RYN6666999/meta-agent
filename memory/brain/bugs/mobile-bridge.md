# mobile-bridge 已知問題

> 蒸餾自 69 個 error-log（2026-03-17 ~ 2026-04-23）。每次新事件只更新「已知事實」區塊，並在時間線 append 一行。

---

## ✅ 目前最佳已知事實（最後更新：2026-04-23 ✅ 已解決）

### 根本問題（已解決 2026-04-23）
**路徑不符：`memory-mcp/` 移至 `tools/memory-mcp/` 後，4 個腳本未更新路徑。**
uvicorn 啟動時 `load_backend()` 找不到 `memory-mcp/server.py` → `FileNotFoundError` → 崩潰。
cloudflared **全程正常**（從未是問題所在，是假陽性誤導）。

### 崩潰鏈（36 天的真相）
```
uvicorn 啟動
→ load_backend() → FileNotFoundError: memory-mcp/server.py 不存在
→ uvicorn 崩潰，port 9901 無服務
→ health check = 000
→ watchdog 記錄「mobile API endpoint not healthy」（假陽性）
→ 重啟 uvicorn → 再次 FileNotFoundError → 無限循環 × 69 次
cloudflared 全程 ALIVE，被誤認為元兇
```

### 修法（已執行，2026-04-23）
```bash
ln -sf /Users/ryan/meta-agent/tools/memory-mcp /Users/ryan/meta-agent/memory-mcp
# 驗收：acceptance 7/7 passed，uvicorn PID 存活
```

### 受影響的 4 個腳本（全部透過 symlink 修復）
| 腳本 | 行號 | 舊路徑（錯誤）|
|------|------|--------|
| `api/server.py` | 32 | `BASE_DIR / "memory-mcp" / "server.py"` |
| `scripts/replay_degraded_queue.py` | 21 | 同上 |
| `scripts/local_memory_extract.py` | 27 | 同上 |
| `scripts/benchmark_debug_capability.py` | 9 | `sys.path.insert(0, REPO / "memory-mcp")` |

### 未來防範
- 若再移動 `tools/memory-mcp/`，symlink 需同步更新
- 考慮在 `common/config.py` 統一定義 `BACKEND_FILE`，避免各腳本各自寫死路徑

### 正確操作指令
```bash
# 重啟
launchctl kickstart -k gui/$(id -u)/com.meta-agent.mobile-bridge

# 查日誌（正確路徑）
tail -f /private/tmp/meta-agent-api.log

# 診斷
pgrep -f "uvicorn.*9901" && echo "uvicorn OK" || echo "uvicorn DEAD"
pgrep -f cloudflared && echo "cloudflared OK" || echo "cloudflared DEAD"

# 驗收
python3 /Users/ryan/meta-agent/scripts/mobile_bridge_acceptance.py
```

---

## 📅 事件時間線（只 append）

- 2026-03-17: 首次記錄。多種症狀：tunnel-down、webhook-bind-failed、url-missing（全為假陽性）
- 2026-03-21: 確認 root_cause = "cloudflared tunnel process not running"（仍為誤判）
- 2026-03-22 ~ 2026-04-22: 每日 api-down + tunnel-down，69 個 error-log，無根本修復
- **2026-04-23: 真正根因確認** — `memory-mcp/server.py` FileNotFoundError 導致 uvicorn 無法啟動
- **2026-04-23: 修復完成** — 建立 symlink，acceptance 7/7 passed

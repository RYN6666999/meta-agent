# 商業級記憶方案落差盤點

## 現況
meta-agent 已有記憶核心、狀態檔、交接、決策留痕與基本自動化，但目前更像「內部作業系統」，還不是可以直接接上別的產品或工作流的外掛大腦。

## 主要落差
1. 對外可用性不足
   缺少標準 HTTP API，只有 MCP 與單一 webhook，外部系統難以直接接入。

2. 記憶品質 metadata 不足
   目前缺少 confidence、usage_count、submitted_by、source_session 等欄位，對商業級召回與排序不夠。

3. 多來源入口未統一
   尚未形成 Telegram / Slack / Web form / CLI 共用的標準 ingest contract。

4. 可觀測性仍偏內部
   健康檢查與 E2E 已有，但尚未以對外 API 形式提供健康與 trace 能力。

## MVP 優先序
1. 建立對外 HTTP API wrapper
2. 補 `health` / `trace` 對外介面
3. 再擴充記憶品質 metadata 與多來源入口

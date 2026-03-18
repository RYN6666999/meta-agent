#!/bin/bash
# install-decision-loop-launchd.sh — 安裝決策自動化循環到 launchd

set -e

BASE_DIR="/Users/ryan/meta-agent"
PLIST_SOURCE="$BASE_DIR/.launchd/com.meta-agent.auto-decision-loop.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.meta-agent.auto-decision-loop.plist"

echo "📦 安裝決策自動化循環到 launchd..."

# 檢查源檔案
if [[ ! -f "$PLIST_SOURCE" ]]; then
    echo "❌ 源檔案不存在：$PLIST_SOURCE"
    exit 1
fi

# 確保目標目錄存在
mkdir -p "$HOME/Library/LaunchAgents"

# 複製 plist 檔案
echo "📋 複製 plist 檔案..."
cp "$PLIST_SOURCE" "$PLIST_DEST"
chmod 644 "$PLIST_DEST"

# 卸載舊的（如果存在）
if launchctl list | grep -q "com.meta-agent.auto-decision-loop"; then
    echo "🔄 卸載舊的服務..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    sleep 1
fi

# 載入新的
echo "🚀 載入新的服務..."
launchctl load "$PLIST_DEST"

# 驗證
if launchctl list | grep -q "com.meta-agent.auto-decision-loop"; then
    echo "✅ 服務已安裝並啟動"
    echo "   Label: com.meta-agent.auto-decision-loop"
    echo "   執行週期: 每小時"
    echo "   Log 檔案:"
    echo "     - 標準輸出: /private/tmp/meta-agent-auto-decision-loop.out.log"
    echo "     - 標準錯誤: /private/tmp/meta-agent-auto-decision-loop.err.log"
else
    echo "❌ 服務載入失敗"
    exit 1
fi

# 手動運行一次進行測試
echo ""
echo "🧪 手動運行一次進行測試..."
python3 "$BASE_DIR/scripts/auto-decision-loop.py"

echo ""
echo "✅ 安裝完成！"
echo "   下次執行時間: ~$(date -u -d "@$(($(date +%s) + 3600))" +%Y-%m-%d\ %H:%M:%S\ UTC)"

#!/bin/bash
# 在桌面建立「會議錄音.command」啟動器
# Usage: bash setup_desktop_launcher.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER="$HOME/Desktop/會議錄音.command"

cat > "$LAUNCHER" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
python3 meeting_recorder_ui.py
EOF

chmod +x "$LAUNCHER"
echo "✓ 啟動器已建立：$LAUNCHER"
echo "  雙擊桌面的「會議錄音」即可啟動。"

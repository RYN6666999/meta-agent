#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER="$HOME/Desktop/會議錄音.command"

cat > "$LAUNCHER" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
python3 meeting_recorder_ui.py
EOF

chmod +x "$LAUNCHER"
echo "✓ 啟動器已建立：$LAUNCHER"

#!/usr/bin/env bash
# deploy.sh — 將 novel-framework-analyzer MCP server 部署到遠端伺服器
# 用法：./deploy.sh <user@host> [domain] [port]
#
# 範例：
#   ./deploy.sh ubuntu@1.2.3.4
#   ./deploy.sh ubuntu@1.2.3.4 novel.yourdomain.com
#   ./deploy.sh ubuntu@1.2.3.4 novel.yourdomain.com 9400
#
# 前置需求：
#   本機     — ssh key 已加入遠端 authorized_keys
#   遠端     — Python 3.10+、pip、sqlite3
#   （可選）遠端 — nginx（自動安裝反代 + HTTPS）

set -euo pipefail

REMOTE="${1:?請提供遠端 user@host，例如 ubuntu@1.2.3.4}"
DOMAIN="${2:-}"
PORT="${3:-9400}"
REMOTE_DIR="/opt/novel-mcp"
SERVICE_NAME="novel-mcp"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "===================================================="
echo " Novel Framework Analyzer MCP Server 遠端部署"
echo " 目標：$REMOTE → $REMOTE_DIR"
echo " 端口：$PORT"
[ -n "$DOMAIN" ] && echo " 域名：$DOMAIN"
echo "===================================================="

# ── 1. 傳輸檔案 ────────────────────────────────────────────────────────────
echo ""
echo "[1/5] 傳輸必要檔案..."
ssh "$REMOTE" "mkdir -p $REMOTE_DIR/services/vector_store $REMOTE_DIR/scripts $REMOTE_DIR/vector_store"

# 核心檔案
rsync -avz --progress \
  "$SCRIPT_DIR/mcp_server.py" \
  "$SCRIPT_DIR/requirements-mcp.txt" \
  "$REMOTE:$REMOTE_DIR/"

# 資料庫（如果存在）
if [ -f "$SCRIPT_DIR/novel_analyzer.db" ]; then
  echo "  → 傳輸 novel_analyzer.db..."
  rsync -avz --progress "$SCRIPT_DIR/novel_analyzer.db" "$REMOTE:$REMOTE_DIR/"
fi

# vector store（如果已建立）
if [ -d "$SCRIPT_DIR/vector_store/chroma" ]; then
  echo "  → 傳輸 ChromaDB 向量庫..."
  rsync -avz --progress "$SCRIPT_DIR/vector_store/" "$REMOTE:$REMOTE_DIR/vector_store/"
fi

# Services
rsync -avz --progress \
  "$SCRIPT_DIR/services/vector_store/" \
  "$REMOTE:$REMOTE_DIR/services/vector_store/"

echo "  ✓ 檔案傳輸完成"

# ── 2. 安裝依賴 ────────────────────────────────────────────────────────────
echo ""
echo "[2/5] 安裝 Python 依賴..."
ssh "$REMOTE" "
  cd $REMOTE_DIR
  python3 -m pip install --quiet --upgrade pip
  pip install --quiet -r requirements-mcp.txt
  echo '  ✓ 依賴安裝完成'
"

# ── 3. 建立 systemd service ─────────────────────────────────────────────────
echo ""
echo "[3/5] 建立 systemd service..."
ssh "$REMOTE" "
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << 'UNIT'
[Unit]
Description=Novel Framework Analyzer MCP Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$REMOTE_DIR
Environment=NOVEL_DB_PATH=$REMOTE_DIR/novel_analyzer.db
Environment=NOVEL_VECTOR_PATH=$REMOTE_DIR/vector_store/chroma
ExecStart=/usr/bin/python3 $REMOTE_DIR/mcp_server.py --transport sse --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}
sleep 2
sudo systemctl status ${SERVICE_NAME} --no-pager | head -20
echo '  ✓ systemd service 啟動完成'
"

# ── 4. nginx 反代 + HTTPS（有域名才做）────────────────────────────────────
if [ -n "$DOMAIN" ]; then
  echo ""
  echo "[4/5] 設定 nginx 反代 + HTTPS（$DOMAIN）..."
  ssh "$REMOTE" "
    # 安裝 nginx、certbot（如未安裝）
    if ! command -v nginx &>/dev/null; then
      sudo apt-get update -q && sudo apt-get install -y -q nginx certbot python3-certbot-nginx
    fi

    sudo tee /etc/nginx/sites-available/${SERVICE_NAME} > /dev/null << 'NGINX'
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass         http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection keep-alive;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_buffering    off;   # SSE 必須關閉 buffer
        proxy_cache        off;
        proxy_read_timeout 86400s;
    }
}
NGINX

    sudo ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    echo '  ✓ nginx 設定完成（HTTP）'
    echo ''
    echo '  申請 HTTPS 憑證...'
    sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || \
      echo '  ⚠️ HTTPS 申請失敗（請確認 DNS 已指向此 IP），之後可手動執行：sudo certbot --nginx -d $DOMAIN'
  "
else
  echo ""
  echo "[4/5] 跳過 nginx（未提供域名），直接使用 http://<server-ip>:$PORT/sse"
fi

# ── 5. 顯示連線設定 ─────────────────────────────────────────────────────────
echo ""
echo "[5/5] 部署完成！"
echo ""
SERVER_IP=$(ssh "$REMOTE" "curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print \$1}'")
if [ -n "$DOMAIN" ]; then
  MCP_URL="https://$DOMAIN/sse"
else
  MCP_URL="http://$SERVER_IP:$PORT/sse"
fi

echo "======================================================"
echo " MCP Server 已上線：$MCP_URL"
echo "======================================================"
echo ""
echo "── Claude Desktop 設定（~/.claude/claude_desktop_config.json）──"
cat << JSON
{
  "mcpServers": {
    "novel-analyzer": {
      "transport": "sse",
      "url": "$MCP_URL"
    }
  }
}
JSON
echo ""
echo "── Cursor / Windsurf 設定 ──"
echo '  MCP URL: '"$MCP_URL"
echo ""
echo "── 本機 stdio 模式（不需部署，直接連本機資料庫）──"
cat << JSON2
{
  "mcpServers": {
    "novel-analyzer": {
      "command": "python3",
      "args": ["$(cd "$SCRIPT_DIR" && pwd)/mcp_server.py"]
    }
  }
}
JSON2

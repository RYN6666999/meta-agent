#!/usr/bin/env bash
# agent-relay.sh — Genspark ↔ Claude Code Relay Server 啟動腳本
#
# 部署：
#   cp host/bin/agent-relay.sh /usr/local/bin/agent-relay.sh
#   chmod 755 /usr/local/bin/agent-relay.sh
#   cp host/launchd/com.agentbot.relay.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.agentbot.relay.plist

set -euo pipefail

GATEWAY_DIR="/Users/ryan/meta-agent/tools/agent-ssh-gateway"
RUNNER_DIR="$GATEWAY_DIR/runner"
NODE_BIN="/Users/ryan/.nvm/versions/node/v20.18.3/bin/node"
TSNODE="$RUNNER_DIR/node_modules/.bin/ts-node"

# 確保目錄存在
mkdir -p "$GATEWAY_DIR/relay/artifacts"

cd "$RUNNER_DIR"
exec "$NODE_BIN" "$TSNODE" src/relay.ts

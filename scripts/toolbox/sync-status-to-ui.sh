#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/Users/ryan/meta-agent"
MEM_DIR="$BASE_DIR/memory"
UI_STATUS_DIR="$BASE_DIR/scripts/toolbox-console/public/toolbox-status"

mkdir -p "$UI_STATUS_DIR"

copy_if_exists() {
  local src="$1"
  local dst="$2"
  if [[ -f "$src" ]]; then
    cp "$src" "$dst"
  fi
}

copy_if_exists "$MEM_DIR/toolbox-health.json" "$UI_STATUS_DIR/toolbox-health.json"
copy_if_exists "$MEM_DIR/douyin-preflight.json" "$UI_STATUS_DIR/douyin-preflight.json"
copy_if_exists "$MEM_DIR/toolbox-prune-report.json" "$UI_STATUS_DIR/toolbox-prune-report.json"

echo "Synced status files to $UI_STATUS_DIR"
ls -1 "$UI_STATUS_DIR"

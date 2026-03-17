#!/bin/bash
# swap-monitor.sh — 當 Swap > 7000MB 或 free% < 20% 時發送桌面通知
# 由 LaunchAgent com.meta-agent.swap-monitor.plist 每 30 秒呼叫一次

THRESHOLD_SWAP=7000
THRESHOLD_FREE=20
LOGFILE="$HOME/meta-agent/memory/status/swap-monitor.log"

swap_used=$(sysctl vm.swapusage | awk -F'used = |M  free' '{printf "%.0f", $2}')
free_pct=$(memory_pressure -Q | awk -F': ' '/free percentage/ {gsub(/%/,"",$2); printf "%.0f", $2}')
ts=$(date '+%F %T')

echo "$ts swap=${swap_used}MB free=${free_pct}%" >> "$LOGFILE"

alert=0
msg=""

if [ "$swap_used" -ge "$THRESHOLD_SWAP" ]; then
    msg="⚠️ Swap ${swap_used}MB（超過 ${THRESHOLD_SWAP}MB 警戒線）"
    alert=1
fi

if [ "$free_pct" -le "$THRESHOLD_FREE" ]; then
    msg="${msg} 🔴 可用記憶體僅剩 ${free_pct}%"
    alert=1
fi

if [ "$alert" -eq 1 ]; then
    echo "$ts ALERT: $msg" >> "$LOGFILE"
    osascript -e "display notification \"$msg\" with title \"記憶體警報\" subtitle \"建議執行 n8n-pause\" sound name \"Basso\""
fi

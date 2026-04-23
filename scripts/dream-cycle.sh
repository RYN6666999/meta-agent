#!/bin/bash
# dream-cycle.sh — 每晚一次的知識維護循環（對標 GBrain Dream Cycle）
#
# 替代以下 launchd agents（合併為單一維護窗口）：
#   - dedup-lightrag
#   - generate-handoff
#   - memory-decay
#   - tiered-summary
#   - truth-xval
#   - persona-tech-radar
#   - obsidian-ingest
#   - reactivate-webhooks
#
# 保留獨立 launchd 的（有即時性需求）：
#   - mobile-bridge（服務本身）
#   - mobile-watchdog（每 60 秒守護）
#   - git-score（每小時評分備份）
#   - swap-monitor（每 30 秒系統監控）
#   - health-check（每天 08:00 健康檢查）
#
# 觸發時機：
#   1. 每晚 02:00 由 launchd 自動觸發
#   2. health/e2e 失敗後手動觸發
#   3. Ryan 直接執行：bash scripts/dream-cycle.sh

set -euo pipefail

REPO="/Users/ryan/meta-agent"
VENV_PY="$REPO/.venv/bin/python"
SYS_PY="/usr/bin/python3"
LOG="$REPO/memory/dream-cycle.log"
STATUS="$REPO/memory/system-status.json"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

run_step() {
    local name="$1"
    local py="$2"
    local script="$3"
    log "▶ $name..."
    if $py "$script" >> "$LOG" 2>&1; then
        log "✅ $name 完成"
        return 0
    else
        log "❌ $name 失敗（繼續下一步）"
        return 1
    fi
}

log "====== Dream Cycle 開始 ======"

# Step 1: 交叉查核知識圖譜（最重要，先跑）
run_step "truth-xval" "$VENV_PY" "$REPO/scripts/truth-xval.py" || true

# Step 2: 知識去重
run_step "dedup-lightrag" "$VENV_PY" "$REPO/scripts/dedup-lightrag.py --dry-run" || true

# Step 3: 記憶衰減清洗
run_step "memory-decay" "$SYS_PY" "$REPO/scripts/memory-decay.py" || true

# Step 4: 分層摘要
run_step "tiered-summary" "$VENV_PY" "$REPO/scripts/memory-tier-summary.py" || true

# Step 5: Obsidian 增量 ingest
run_step "obsidian-ingest" "$VENV_PY" "$REPO/scripts/obsidian-ingest.py" || true

# Step 6: 人格庫技術雷達更新
run_step "persona-tech-radar" "$VENV_PY" "$REPO/scripts/persona_tech_radar.py" || true

# Step 7: Webhook 重新激活（確保 n8n 活著）
run_step "reactivate-webhooks" "$SYS_PY" "$REPO/scripts/reactivate_webhooks.py" || true

# Step 8: inbox/ 清理（7 天以上未處理 → 歸檔）
log "▶ inbox 清理..."
INBOX="$REPO/memory/brain/inbox"
ARCHIVE="$REPO/memory/archive"
count=0
for f in "$INBOX"/*.md; do
    [ -f "$f" ] || continue
    [ "$(basename $f)" = "README.md" ] && continue
    # 從檔名取日期
    fdate=$(basename "$f" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' || echo "")
    if [ -n "$fdate" ]; then
        age=$(( ( $(date +%s) - $(date -j -f "%Y-%m-%d" "$fdate" +%s 2>/dev/null || echo 0) ) / 86400 ))
        if [ "$age" -gt 7 ]; then
            mv "$f" "$ARCHIVE/" && log "  📦 歸檔 $(basename $f)（${age} 天）"
            count=$((count+1))
        fi
    fi
done
log "✅ inbox 清理完成（歸檔 $count 條）"

# Step 9: 最後更新 handoff（Dream Cycle 完成後）
run_step "generate-handoff" "$SYS_PY" "$REPO/scripts/generate-handoff.py" || true

# Step 10: 更新 dream-cycle 執行時間到 system-status.json
if [ -f "$STATUS" ]; then
    now=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    # 用 python 安全更新 json（避免 sed 破壞結構）
    $SYS_PY -c "
import json, sys
with open('$STATUS') as f:
    s = json.load(f)
s['dream_cycle_last_run'] = '$now'
with open('$STATUS', 'w') as f:
    json.dump(s, f, ensure_ascii=False, indent=2)
print('system-status updated')
" 2>/dev/null || true
fi

log "====== Dream Cycle 完成 ======"

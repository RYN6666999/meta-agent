#!/bin/bash
# extract-session.sh — 手動呼叫：把指定文字送 n8n 萃取
# 用法：
#   echo "對話內容..." | bash extract-session.sh
#   bash extract-session.sh "直接傳文字"
#   bash extract-session.sh < conversation.txt
#
# 也可在 Claude Code 裡直接說：「萃取這段對話」

set -e

WEBHOOK="http://localhost:5678/webhook/9ABqAtFoJWHmhkEa/webhook/memory-extract"
SESSION_ID="session-$(date +%Y%m%d-%H%M%S)"

if [ $# -ge 1 ]; then
    CONVERSATION="$1"
elif [ ! -t 0 ]; then
    CONVERSATION=$(cat)
else
    echo "用法: bash extract-session.sh '對話內容'" >&2
    echo "  或: echo '對話內容' | bash extract-session.sh" >&2
    exit 1
fi

# 字數檢查
CHAR_COUNT=${#CONVERSATION}
if [ "$CHAR_COUNT" -lt 100 ]; then
    echo "❌ 內容太短 (${CHAR_COUNT} 字 < 100)，跳過" >&2
    exit 1
fi

echo "📤 送出萃取 (${CHAR_COUNT} 字)..."

RESULT=$(curl -s -X POST "$WEBHOOK" \
    -H "Content-Type: application/json" \
    -d "{\"conversation\": $(echo "$CONVERSATION" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'), \"session_id\": \"$SESSION_ID\"}" \
    --max-time 60)

echo "$RESULT" | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get('summary', d))
except:
    print(sys.stdin.read())
" 2>/dev/null || echo "$RESULT"

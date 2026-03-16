#!/usr/bin/env python3
"""
里程碑裁判 (Milestone Judge)

觸發時機：Phase 3 Exit 0 — 工序驗證通過後由 Claude 主動呼叫。
職責：判斷此次里程碑是否屬於「重大決策/突破」。

核心模式：
- 預設：評分未提交變更（commit 前）
- --from-commit A..B：評分已提交變更（commit 後），補齊觸發因果鏈

評分達標後：寫入 pending-decisions（等待人類 approve）
"""

import argparse
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
import json
from datetime import datetime
from pathlib import Path

REPO_DIR = Path("/Users/ryan/meta-agent")
BRANCH_THRESHOLD = 60
JUDGE_LOG = REPO_DIR / "memory" / "milestone-judge-log.md"

MAJOR_WEIGHTS = {
    "law_forbidden": 80,
    "law_other": 40,
    "tech_stack_new": 70,
    "tech_stack_mod": 50,
    "truth_source": 60,
    "error_log_new": 50,
    "scripts_core": 40,
    "other": 10,
}


def run_git(args):
    result = subprocess.run(
        ["git"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.returncode


def get_uncommitted_files():
    stdout, _ = run_git(["status", "--porcelain"])
    if not stdout:
        return []
    files = []
    for line in stdout.splitlines():
        m = re.match(r"^(.{2}) (.+)$", line)
        if not m:
            continue
        status = m.group(1).strip()
        filepath = m.group(2)
        files.append((status, filepath))
    return files


def get_files_from_commit_range(commit_range):
    stdout, code = run_git(["diff", "--name-status", commit_range])
    if code != 0 or not stdout:
        return []

    files = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        raw_status = parts[0].strip()
        status = raw_status[0]
        filepath = parts[-1].strip()
        files.append((status, filepath))
    return files


def get_diff_content(commit_range=None):
    if commit_range:
        stdout, _ = run_git(["diff", commit_range])
        return stdout

    stdout, _ = run_git(["diff", "--cached", "HEAD"])
    if not stdout:
        stdout, _ = run_git(["diff", "HEAD"])
    return stdout


def score_file(status, filepath, diff_content):
    if "law.json" in filepath:
        if '"forbidden"' in diff_content or ('"rule"' in diff_content and '"reason"' in diff_content):
            pts = MAJOR_WEIGHTS["law_forbidden"]
            return pts, f"law.json forbidden規則變更 +{pts}"
        pts = MAJOR_WEIGHTS["law_other"]
        return pts, f"law.json 其他修改 +{pts}"

    if filepath.startswith("tech-stack/"):
        key = "tech_stack_new" if status == "A" else "tech_stack_mod"
        pts = MAJOR_WEIGHTS[key]
        verb = "新增" if status == "A" else "修改"
        return pts, f"tech-stack {verb} {filepath} +{pts}"

    if filepath.startswith("truth-source/") and status == "A":
        pts = MAJOR_WEIGHTS["truth_source"]
        return pts, f"truth-source 新增驗證決策 {filepath} +{pts}"

    if filepath.startswith("error-log/") and status == "A":
        pts = MAJOR_WEIGHTS["error_log_new"]
        return pts, f"error-log 新增根因 {filepath} +{pts}"

    if filepath.startswith("scripts/"):
        pts = MAJOR_WEIGHTS["scripts_core"]
        return pts, f"核心腳本變更 {filepath} +{pts}"

    pts = MAJOR_WEIGHTS["other"]
    return pts, f"其他變更 {filepath} +{pts}"


def calculate_score(files, commit_range=None):
    diff_content = get_diff_content(commit_range)
    total = 0
    signals = []
    for status, filepath in files:
        pts, label = score_file(status, filepath, diff_content)
        total += pts
        signals.append(f"  {label}")
    return total, signals


def create_decision_branch(topic, description, score, signals):
    """建立 decision/ 分支並 commit"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    branch_name = f"decision/{topic}-{date_str}"

    # 建立並切換到新分支
    _, code = run_git(["checkout", "-b", branch_name])
    if code != 0:
        # 分支已存在則直接切換
        run_git(["checkout", branch_name])

    # 加入所有變更
    run_git(["add", "-A"])

    # commit
    msg = f"milestone: [{topic}] score={score} 重大決策備份\n\n{description}"
    _, code = run_git(["commit", "-m", msg])
    if code != 0:
        return False, branch_name, "commit 失敗（可能無變更）"

    # 寫 truth-source 記錄
    write_truth_source(topic, description, score, signals, branch_name, date_str)

    # 切回 main
    run_git(["checkout", "main"])

    return True, branch_name, "成功"


def ingest_to_lightrag(title: str, content: str) -> tuple[bool, str]:
    """直接 POST 到 LightRAG /documents/text（非同步，失敗不中斷主流程）"""
    payload = json.dumps({
        "text": content,
        "description": title
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            "http://localhost:9621/documents/text",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)


def write_truth_source(topic, description, score, signals, branch_name, date_str):
    """在 truth-source/ 留下決策記錄，並同步 ingest 到 LightRAG"""
    truth_dir = REPO_DIR / "truth-source"
    truth_dir.mkdir(exist_ok=True)

    filename = truth_dir / f"{date_str}-{topic}.md"
    content = f"""---
date: {date_str}
type: verified_truth
status: active
last_triggered: {date_str}
expires_after_days: 365
source: milestone-judge（自動生成）
branch: {branch_name}
score: {score}
---

# {topic}

## 描述
{description}

## 評分信號
{chr(10).join(signals)}

**總分：{score} / 閾值 {BRANCH_THRESHOLD}**

## 分支
`{branch_name}` — 此分支為本決策的真理源，供未來對照。
"""
    filename.write_text(content, encoding="utf-8")

    # ── 同步 ingest 到 LightRAG（真理源三角第三邊）──
    ok, detail = ingest_to_lightrag(
        f"【決策記錄】{topic} ({date_str})",
        content
    )
    if ok:
        print(f"   ✅ LightRAG 已同步：{topic}")
    else:
        print(f"   ⚠️  LightRAG 同步失敗（非阻斷）：{detail}")


def append_pending_decision(topic, description, score, signals, source="working-tree"):
    """寫入決策收件匣 memory/pending-decisions.md，等待人類判斷"""
    pending_file = REPO_DIR / "memory" / "pending-decisions.md"
    date_str = datetime.now().strftime("%Y-%m-%d")
    signals_summary = "; ".join(s.strip() for s in signals[:2])
    desc = f"{description[:48]} [{source}]"
    entry = f"| {date_str} | {topic} | {desc} | {score} | {signals_summary} | pending |\n"
    if pending_file.exists():
        content = pending_file.read_text(encoding="utf-8")
        marker = "<!-- AI 偵測到重大決策時，自動在此插入列 -->"
        if marker in content:
            content = content.replace(marker, entry + marker)
        else:
            content += entry
        pending_file.write_text(content, encoding="utf-8")
    else:
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text(
            "# 決策收件匣\n\n| date | topic | description | score | signals | status |\n"
            "|------|-------|-------------|-------|---------|--------|\n" + entry
        , encoding="utf-8")


def execute_approved(topic):
    """讀 pending-decisions.md，找到 approved 的 topic 並執行"""
    pending_file = REPO_DIR / "memory" / "pending-decisions.md"
    if not pending_file.exists():
        print(f"❌ pending-decisions.md 不存在")
        return 1

    content = pending_file.read_text(encoding="utf-8")
    found = None
    target_line = None
    for line in content.splitlines():
        if f"| {topic} |" in line and "| approved |" in line:
            parts = [p.strip() for p in line.split("|")]
            found = {
                "date": parts[1],
                "topic": parts[2],
                "description": parts[3],
                "score": int(parts[4]) if parts[4].isdigit() else 0,
                "signals": parts[5].split("; "),
            }
            target_line = line
            break

    if not found:
        print(f"❌ 找不到 topic='{topic}' 且 status=approved 的決策")
        print(f"   提示：先說 'approve {topic}' 確認，再執行 --approve")
        return 1

    print(f"✅ 執行核准決策：{topic} (score={found['score']})")
    success, branch_name, msg = create_decision_branch(
        found["topic"], found["description"], found["score"],
        [f"  {s}" for s in found["signals"]]
    )
    if success:
        done_line = target_line.replace("| approved |", f"| done:{branch_name} |")
        content = content.replace(target_line, done_line)
        pending_file.write_text(content, encoding="utf-8")
        log_result(topic, found['description'], found['score'], found['signals'], True, branch_name)
        print(f"   分支：{branch_name}")
        print(f"   pending-decisions.md 已更新為 done")
    else:
        print(f"❌ 建立分支失敗：{msg}")
        return 1
    return 0

def log_result(topic, description, score, signals, branched, branch_name="", reason=""):
    """寫入裁判日誌"""
    JUDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if branched:
        verdict = f"✅ 重大里程碑 → 建立分支 `{branch_name}`"
    elif reason.startswith("pending human approval"):
        verdict = f"📥 達到閾值（{score}/{BRANCH_THRESHOLD}）→ 已送決策匣，待人類核准"
    else:
        verdict = f"⏳ 未達閾值（{score}/{BRANCH_THRESHOLD}）→ 不建分支{f'，{reason}' if reason else ''}"

    entry = f"""
## {now} | {topic} | 分數 {score} | {verdict}

**描述：** {description}

**評分明細：**
{chr(10).join(signals) if signals else '  （無變更）'}

---
"""
    with open(JUDGE_LOG, "a", encoding="utf-8") as f:
        f.write(entry)


def main():
    parser = argparse.ArgumentParser(description="里程碑裁判 — 偵測重大決策，送交人類判斷")
    parser.add_argument("--topic", help="里程碑主題（英文 kebab-case）")
    parser.add_argument("--description", help="完成了什麼？驗證了什麼？")
    parser.add_argument("--dry-run", action="store_true", help="只評分，不寫收件匣")
    parser.add_argument("--approve", metavar="TOPIC", help="執行已核准的決策（建立 decision/ 分支）")
    parser.add_argument("--from-commit", metavar="RANGE", help="用 commit 區間評分，例如 HEAD~1..HEAD")
    args = parser.parse_args()

    os.chdir(REPO_DIR)

    # ── 執行核准的決策 ───────────────────────────────────────
    if args.approve:
        return execute_approved(args.approve)

    if not args.topic or not args.description:
        parser.error("--topic 和 --description 為必填（除非使用 --approve）")

    print(f"\n🔍 里程碑裁判啟動")
    print(f"   主題：{args.topic}")
    print(f"   描述：{args.description}")
    print(f"   閾值：{BRANCH_THRESHOLD} 分\n")

    source = "working-tree"
    if args.from_commit:
        files = get_files_from_commit_range(args.from_commit)
        source = f"commit:{args.from_commit}"
    else:
        files = get_uncommitted_files()

    if not files:
        if args.from_commit:
            print(f"⚠️  commit 區間 {args.from_commit} 無變更，無法評分")
            log_result(args.topic, args.description, 0, [], False, reason=f"無變更 ({args.from_commit})")
        else:
            print("⚠️  無未提交變更，無法評分")
            print("   提示：請在工序完成後、commit 前呼叫裁判，或使用 --from-commit")
            log_result(args.topic, args.description, 0, [], False, reason="無未提交變更")
        return 1

    score, signals = calculate_score(files, commit_range=args.from_commit)

    print(f"📊 評分結果：{score} / {BRANCH_THRESHOLD}")
    for s in signals:
        print(s)

    if score >= BRANCH_THRESHOLD:
        print(f"\n🚨 達到閾值！偵測到重大里程碑")
        if args.dry_run:
            print("   [dry-run] 不寫入收件匣")
            log_result(args.topic, args.description, score, signals, False, reason="dry-run")
        else:
            # ⬇ 哲學變更：不自動建分支，送交人類判斷
            append_pending_decision(args.topic, args.description, score, signals, source=source)
            log_result(args.topic, args.description, score, signals, False, reason=f"pending human approval ({source})")
            print(f"📥 已寫入 memory/pending-decisions.md")
            print(f"   說 'approve {args.topic}' 確認後由 AI 建立 decision/ 分支")
    else:
        print(f"\n⏳ 未達閾值，不建分支（日常變更，交由 git-score.py 備份）")
        log_result(args.topic, args.description, score, signals, False)

    return 0


if __name__ == "__main__":
    sys.exit(main())

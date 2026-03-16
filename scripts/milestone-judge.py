#!/usr/bin/env python3
"""
里程碑裁判 (Milestone Judge)

觸發時機：Phase 3 Exit 0 — 工序驗證通過後由 Claude 主動呼叫
職責：判斷此次里程碑是否屬於「重大決策/突破」
- 分數 >= 60 → 建立 decision/ 分支，commit，寫 truth-source log
- 分數 <  60 → 僅記錄日誌，不建分支（交給 git-score.py 日常備份）

用法：
  python3 scripts/milestone-judge.py --topic "memory-decay-engine" --description "實作遺忘曲線引擎，驗證通過"
  python3 scripts/milestone-judge.py --topic "replace-lightrag" --description "以 Chroma 取代 LightRAG，效能提升 3x"
"""

import re
import subprocess
import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

REPO_DIR = Path("/Users/ryan/meta-agent")
BRANCH_THRESHOLD = 60
JUDGE_LOG = REPO_DIR / "memory" / "milestone-judge-log.md"

# 質量評分權重（以「影響未來決策的不可逆程度」為標準）
MAJOR_WEIGHTS = {
    "law_forbidden":  80,   # law.json forbidden 新增/修改 → 血淚規則
    "law_other":      40,   # law.json 其他欄位修改
    "tech_stack_new": 70,   # tech-stack/ 新增文件 → 技術棧改變
    "tech_stack_mod": 50,   # tech-stack/ 修改現有文件
    "truth_source":   60,   # truth-source/ 新增驗證決策
    "error_log_new":  50,   # error-log/ 新增系統性根因
    "scripts_core":   40,   # scripts/ 核心腳本變更
    "other":          10,   # 其他
}


def run_git(args, check=False):
    result = subprocess.run(
        ["git"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.returncode


def get_uncommitted_files():
    stdout, _ = run_git(["status", "--porcelain"])
    if not stdout:
        return []
    files = []
    for line in stdout.splitlines():
        m = re.match(r'^(.{2}) (.+)$', line)
        if m:
            status = m.group(1).strip()
            filepath = m.group(2)
            files.append((status, filepath))
    return files


def get_diff_content():
    """取得完整 diff 內容以分析 law.json 的具體變動"""
    stdout, _ = run_git(["diff", "--cached", "HEAD"])
    if not stdout:
        stdout, _ = run_git(["diff", "HEAD"])
    return stdout


def score_file(status, filepath, diff_content):
    """對單一檔案計算分數，回傳 (分數, 說明)"""

    # law.json — 細分 forbidden vs 其他
    if "law.json" in filepath:
        # 檢查 diff 是否涉及 forbidden 陣列
        if '"forbidden"' in diff_content or ('"rule"' in diff_content and '"reason"' in diff_content):
            return MAJOR_WEIGHTS["law_forbidden"], f"law.json forbidden規則變更 +{MAJOR_WEIGHTS['law_forbidden']}"
        else:
            return MAJOR_WEIGHTS["law_other"], f"law.json 其他修改 +{MAJOR_WEIGHTS['law_other']}"

    # tech-stack/ — 新增 vs 修改
    if filepath.startswith("tech-stack/"):
        if status == "A":
            return MAJOR_WEIGHTS["tech_stack_new"], f"tech-stack 新增 {filepath} +{MAJOR_WEIGHTS['tech_stack_new']}"
        else:
            return MAJOR_WEIGHTS["tech_stack_mod"], f"tech-stack 修改 {filepath} +{MAJOR_WEIGHTS['tech_stack_mod']}"

    # truth-source/ 新增驗證決策
    if filepath.startswith("truth-source/") and status == "A":
        return MAJOR_WEIGHTS["truth_source"], f"truth-source 新增驗證決策 {filepath} +{MAJOR_WEIGHTS['truth_source']}"

    # error-log/ 新增系統性根因
    if filepath.startswith("error-log/") and status == "A":
        return MAJOR_WEIGHTS["error_log_new"], f"error-log 新增根因 {filepath} +{MAJOR_WEIGHTS['error_log_new']}"

    # scripts/ 核心腳本
    if filepath.startswith("scripts/"):
        return MAJOR_WEIGHTS["scripts_core"], f"核心腳本變更 {filepath} +{MAJOR_WEIGHTS['scripts_core']}"

    return MAJOR_WEIGHTS["other"], f"其他變更 {filepath} +{MAJOR_WEIGHTS['other']}"


def calculate_score(files):
    diff_content = get_diff_content()
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


def write_truth_source(topic, description, score, signals, branch_name, date_str):
    """在 truth-source/ 留下決策記錄"""
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


def log_result(topic, description, score, signals, branched, branch_name="", reason=""):
    """寫入裁判日誌"""
    JUDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if branched:
        verdict = f"✅ 重大里程碑 → 建立分支 `{branch_name}`"
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
    parser = argparse.ArgumentParser(description="里程碑裁判 — 判斷是否建立 decision/ 分支")
    parser.add_argument("--topic", required=True, help="里程碑主題（用於分支名稱，英文 kebab-case）")
    parser.add_argument("--description", required=True, help="完成了什麼？驗證了什麼？")
    parser.add_argument("--dry-run", action="store_true", help="只評分，不實際建立分支")
    args = parser.parse_args()

    os.chdir(REPO_DIR)

    print(f"\n🔍 里程碑裁判啟動")
    print(f"   主題：{args.topic}")
    print(f"   描述：{args.description}")
    print(f"   閾值：{BRANCH_THRESHOLD} 分\n")

    files = get_uncommitted_files()
    if not files:
        print("⚠️  無未提交變更，無法評分")
        print("   提示：請在工序完成後、commit 前呼叫裁判")
        log_result(args.topic, args.description, 0, [], False, reason="無未提交變更")
        return 1

    score, signals = calculate_score(files)

    print(f"📊 評分結果：{score} / {BRANCH_THRESHOLD}")
    for s in signals:
        print(s)

    if score >= BRANCH_THRESHOLD:
        print(f"\n🚨 達到閾值！此為重大里程碑")
        if args.dry_run:
            print("   [dry-run] 不實際建立分支")
            log_result(args.topic, args.description, score, signals, False, reason="dry-run")
        else:
            success, branch_name, msg = create_decision_branch(args.topic, args.description, score, signals)
            log_result(args.topic, args.description, score, signals, success, branch_name)
            if success:
                print(f"✅ 分支已建立：{branch_name}")
                print(f"   truth-source 記錄已寫入")
                print(f"   已切回 main")
            else:
                print(f"❌ 建立分支失敗：{msg}")
                return 1
    else:
        print(f"\n⏳ 未達閾值，不建分支（日常變更，交由 git-score.py 備份）")
        log_result(args.topic, args.description, score, signals, False)

    return 0


if __name__ == "__main__":
    sys.exit(main())

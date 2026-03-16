#!/usr/bin/env python3
"""
meta-agent Git 評分自動提交器
當累積變更分數超過閾值時自動 git commit

評分邏輯：
- error_fix 新增/修改   = 30 分（最高優先，防止血淚再現）
- tech_decision 變更    = 20 分（架構決策需立即備份）
- verified_truth 新增   = 15 分（驗證通過的事實）
- law.json 變更         = 25 分（法典修改最重要）
- 其他 .md 變更         =  5 分
- 未提交超過 4 小時     = 20 分（時間壓力加分）
- 未提交超過 8 小時     = 40 分

閾值：50 分 → 自動 commit
"""

import re
import subprocess
import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path("/Users/ryan/meta-agent")
THRESHOLD = 50
LOG_FILE = REPO_DIR / "memory" / "git-score-log.md"

# 各類型分數權重
WEIGHTS = {
    "law.json":          25,
    "error-log/":        30,
    "truth-source/":     15,
    "tech-stack/":       20,
    "memory/":           10,
    "other":              5,
}

def run_git(args):
    result = subprocess.run(
        ["git"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.returncode

def get_uncommitted_files():
    """取得所有未提交的變更檔案"""
    stdout, _ = run_git(["status", "--porcelain"])
    if not stdout:
        return []
    files = []
    for line in stdout.splitlines():
        # porcelain 格式：XY<space>filepath（XY 固定 2 字元）
        m = re.match(r'^(.{2}) (.+)$', line)
        if m:
            status = m.group(1).strip()
            filepath = m.group(2)
            files.append((status, filepath))
    return files

def get_hours_since_last_commit():
    """計算距上次 commit 的小時數"""
    stdout, code = run_git(["log", "-1", "--format=%ct"])
    if code != 0 or not stdout:
        return 999  # 從未 commit 過
    last_commit_ts = int(stdout)
    now_ts = datetime.now(timezone.utc).timestamp()
    return (now_ts - last_commit_ts) / 3600

def calculate_score(files, hours_since_commit):
    """計算總分"""
    score = 0
    breakdown = []

    for status, filepath in files:
        if "law.json" in filepath:
            pts = WEIGHTS["law.json"]
            breakdown.append(f"  law.json 變更 +{pts}")
        elif filepath.startswith("error-log/"):
            pts = WEIGHTS["error-log/"]
            breakdown.append(f"  error_fix 變更 ({filepath}) +{pts}")
        elif filepath.startswith("truth-source/"):
            pts = WEIGHTS["truth-source/"]
            breakdown.append(f"  verified_truth 變更 ({filepath}) +{pts}")
        elif filepath.startswith("tech-stack/"):
            pts = WEIGHTS["tech-stack/"]
            breakdown.append(f"  tech_decision 變更 ({filepath}) +{pts}")
        elif filepath.startswith("memory/"):
            pts = WEIGHTS["memory/"]
            breakdown.append(f"  memory 變更 ({filepath}) +{pts}")
        else:
            pts = WEIGHTS["other"]
            breakdown.append(f"  其他變更 ({filepath}) +{pts}")
        score += pts

    # 時間加分
    if hours_since_commit >= 8:
        score += 40
        breakdown.append(f"  未提交 {hours_since_commit:.1f}h (>8h) +40")
    elif hours_since_commit >= 4:
        score += 20
        breakdown.append(f"  未提交 {hours_since_commit:.1f}h (>4h) +20")

    return score, breakdown

def auto_commit(files, score):
    """執行自動 commit"""
    # 加入所有變更
    run_git(["add", "-A"])

    # 產生 commit 訊息
    changed_types = set()
    for _, fp in files:
        if "error-log" in fp:
            changed_types.add("error_fix")
        elif "tech-stack" in fp:
            changed_types.add("tech_decision")
        elif "truth-source" in fp:
            changed_types.add("verified_truth")
        elif "law.json" in fp:
            changed_types.add("law")
        else:
            changed_types.add("misc")

    type_str = "+".join(sorted(changed_types))
    msg = f"auto: [{type_str}] score={score} 超過閾值 {THRESHOLD} 自動備份"

    _, code = run_git(["commit", "-m", msg])
    return code == 0

def log_result(score, breakdown, committed, files):
    """寫入評分日誌"""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = "✅ 自動 commit" if committed else f"⏳ 分數 {score}/{THRESHOLD}，未達閾值"

    entry = f"\n## {now} | 分數：{score} | {status}\n"
    if breakdown:
        entry += "\n".join(breakdown) + "\n"
    if committed:
        entry += f"  → commit 成功（{len(files)} 個檔案）\n"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

def main():
    os.chdir(REPO_DIR)
    files = get_uncommitted_files()

    if not files:
        print("✓ 無未提交變更")
        return 0

    hours = get_hours_since_last_commit()
    score, breakdown = calculate_score(files, hours)

    print(f"📊 評分結果：{score}/{THRESHOLD}")
    for line in breakdown:
        print(line)

    if score >= THRESHOLD:
        print(f"\n🚨 超過閾值 {THRESHOLD}，自動 commit...")
        success = auto_commit(files, score)
        log_result(score, breakdown, success, files)
        print("✅ commit 完成" if success else "❌ commit 失敗")
        # 自動觸發里程碑裁判（只在有 law/tech-stack/truth-source 變更時才有意義）
        import subprocess as _sp
        high_value = any(
            f.startswith(("law.json", "tech-stack/", "truth-source/", "error-log/"))
            for _, f in files
        )
        if high_value:
            _sp.run([
                "python3", str(REPO_DIR / "scripts" / "milestone-judge.py"),
                "--topic", "auto-git-score",
                "--description", f"git-score 自動 commit（score={score}），含重要變更"
            ], cwd=REPO_DIR)
        return 0 if success else 1
    else:
        print(f"\n⏳ 分數未達 {THRESHOLD}，暫不 commit")
        log_result(score, breakdown, False, files)
        return 0

if __name__ == "__main__":
    sys.exit(main())

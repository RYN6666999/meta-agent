#!/usr/bin/env python3
"""
三真理源交叉驗證器 (Truth Cross-Validator)

三個真理源：
  1. truth-source/  — 本地 Markdown 決策記錄
  2. Git decision/  — 不可篡改分支快照
  3. LightRAG       — 語意知識圖譜（port 9621）

每日 08:05 由 launchd 執行（health_check 之後）。
也可手動：python3 scripts/truth-xval.py

輸出：
  - 終端摘要
  - machine-readable 狀態寫入 memory/system-status.json["truth_xval"]
  - 不一致項目寫入 error-log/
"""

import json
import re
import sys
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from common.config import BASE_DIR, ERROR_LOG_DIR, LIGHTRAG_API, STATUS_FILE, TRUTH_SOURCE_DIR
from common.frontmatter import parse_frontmatter_block
from common.status_store import load_status, save_status

REPO_DIR = BASE_DIR
TRUTH_DIR = TRUTH_SOURCE_DIR


# ── 工具函式 ────────────────────────────────────────────────────

def run_git(args):
    result = subprocess.run(
        ["git"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.returncode


def lightrag_health() -> bool:
    try:
        with urllib.request.urlopen(f"{LIGHTRAG_API}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def lightrag_query(query: str) -> tuple[bool, int]:
    """
    對 LightRAG 查詢，回傳 (有結果, 結果數)。
    使用 POST /query（local 模式，只查語境）。
    """
    payload = json.dumps({
        "query": query,
        "mode": "local",
        "top_k": 3,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{LIGHTRAG_API}/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200:
                return False, 0
            body = json.loads(r.read().decode("utf-8"))
            # LightRAG 回傳 {"response": "...", "sources": [...]}
            response_text = body.get("response", "")
            if not response_text or "no relevant" in response_text.lower():
                return False, 0
            return True, 1
    except Exception as exc:
        print(f"[truth-xval][warn] lightrag query failed: {exc}", file=sys.stderr)
        return False, 0


def git_branch_exists(branch_name: str) -> bool:
    stdout, code = run_git(["branch", "--list", branch_name])
    return bool(stdout.strip())


def parse_frontmatter(path: Path) -> dict:
    """讀取 YAML frontmatter（共用 parser，支援 key: value 基礎格式）"""
    text = path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter_block(text)
    return fm


# ── 核心驗證邏輯 ─────────────────────────────────────────────────

def validate_truth_sources(lightrag_ok: bool) -> dict:
    """
    掃描 truth-source/*.md，逐一驗證三真理源一致性。
    回傳驗證報告 dict。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    results = []

    truth_files = sorted(TRUTH_DIR.glob("*.md"))
    if not truth_files:
        return {
            "checked_at": now,
            "total": 0,
            "ok": 0,
            "warn": 0,
            "error": 0,
            "lightrag_available": lightrag_ok,
            "details": [],
        }

    for tf in truth_files:
        if tf.name == "decision-template.md":
            continue  # 模板，跳過

        fm = parse_frontmatter(tf)
        topic = tf.stem  # e.g. 2026-03-16-pdca-causal-chain
        branch = fm.get("branch", "")
        score = fm.get("score", "?")

        checks = {}

        # ① truth-source/ 檔案存在 — 這裡就是入口，一定算 ✅
        checks["local_file"] = True

        # ② Git decision/ 分支是否存在
        if branch:
            checks["git_branch"] = git_branch_exists(branch)
        else:
            checks["git_branch"] = None  # 無分支欄位（舊格式/手動建的）

        # ③ LightRAG 是否能查到
        if lightrag_ok:
            # 用 topic 關鍵字查詢（去掉日期前綴作為查詢詞）
            query_keyword = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", topic)
            query_keyword = query_keyword.replace("-", " ")
            found, _ = lightrag_query(query_keyword)
            checks["lightrag"] = found
        else:
            checks["lightrag"] = None  # LightRAG 不可用

        # 判定狀態
        branch_ok = checks["git_branch"] is not False  # None 算 warn 不算 error
        lightrag_status = checks["lightrag"]

        if branch_ok and lightrag_status is True:
            status = "ok"
        elif lightrag_status is None:
            status = "warn"  # LightRAG 不可用，無法確認
        elif not branch_ok:
            status = "error"
        else:
            status = "warn"  # LightRAG 查無 → 需補 ingest

        results.append({
            "file": tf.name,
            "topic": topic,
            "branch": branch,
            "score": score,
            "checks": checks,
            "status": status,
        })

    ok_count = sum(1 for r in results if r["status"] == "ok")
    warn_count = sum(1 for r in results if r["status"] == "warn")
    err_count = sum(1 for r in results if r["status"] == "error")

    return {
        "checked_at": now,
        "total": len(results),
        "ok": ok_count,
        "warn": warn_count,
        "error": err_count,
        "lightrag_available": lightrag_ok,
        "details": results,
    }


def repair_missing_lightrag(details: list) -> list:
    """
    對 LightRAG 查無的項目，嘗試重新 ingest truth-source 檔案。
    回傳被修復的 topic 清單。
    """
    repaired = []
    for item in details:
        if item["status"] != "warn" or item["checks"].get("lightrag") is not False:
            continue  # 只處理 lightrag=False（查無）的 warn
        tf = TRUTH_DIR / item["file"]
        if not tf.exists():
            continue
        content = tf.read_text(encoding="utf-8")
        title = f"【決策記錄】{item['topic']}"
        payload = json.dumps({
            "text": content,
            "description": title,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"{LIGHTRAG_API}/documents/text",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    repaired.append(item["topic"])
                    item["repaired"] = True
        except Exception as exc:
            item["repair_error"] = str(exc)[:200]
            print(f"[truth-xval][warn] repair ingest failed for {item['topic']}: {exc}", file=sys.stderr)
    return repaired


def write_error_log(report: dict) -> None:
    """若有 error 項目，寫入 error-log/"""
    errors = [r for r in report["details"] if r["status"] == "error"]
    if not errors:
        return
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = ERROR_LOG_DIR / f"{date_str}-truth-xval-errors.md"
    ERROR_LOG_DIR.mkdir(exist_ok=True)
    lines = [
        f"# 三真理源不一致 — {report['checked_at']}\n",
        "| topic | branch | git_ok | lightrag |\n",
        "|-------|--------|--------|----------|\n",
    ]
    for r in errors:
        git_ok = "✅" if r["checks"]["git_branch"] else "❌"
        lr = "✅" if r["checks"]["lightrag"] else ("⚠️" if r["checks"]["lightrag"] is None else "❌")
        lines.append(f"| {r['topic']} | {r['branch']} | {git_ok} | {lr} |\n")
    log_path.write_text("".join(lines), encoding="utf-8")


# ── 主程式 ───────────────────────────────────────────────────────

def main():
    print("🔍 三真理源交叉驗證器")
    print("=" * 52)

    lightrag_ok = lightrag_health()
    if not lightrag_ok:
        print("⚠️  LightRAG 不可用 — 跳過圖譜驗證（其他兩源仍驗證）")
    else:
        print("✅ LightRAG 連線正常")

    report = validate_truth_sources(lightrag_ok)

    if report["total"] == 0:
        print("ℹ️  truth-source/ 目前無決策記錄，跳過。")
    else:
        # 嘗試修復 LightRAG 查無的項目
        if lightrag_ok:
            repaired = repair_missing_lightrag(report["details"])
            if repaired:
                print(f"🔧 自動補 ingest {len(repaired)} 筆進 LightRAG：{repaired}")

        # 打印摘要
        print(f"\n📊 驗證結果（共 {report['total']} 筆決策）")
        print(f"   ✅ 三源一致：{report['ok']} 筆")
        print(f"   ⚠️  警告（LightRAG 查無或不可用）：{report['warn']} 筆")
        print(f"   ❌ 錯誤（git 分支不存在）：{report['error']} 筆")

        for r in report["details"]:
            git_icon = "✅" if r["checks"]["git_branch"] else ("➖" if r["checks"]["git_branch"] is None else "❌")
            lr_val = r["checks"]["lightrag"]
            lr_icon = "✅" if lr_val else ("⚠️" if lr_val is None else "⚡修復" if r.get("repaired") else "⚠️")
            print(f"   {r['status'].upper():5s} | {r['file'][:45]} | git:{git_icon} lightrag:{lr_icon}")

        if report["error"] > 0:
            write_error_log(report)
            print(f"\n❌ {report['error']} 筆 error 已寫入 error-log/")

    # ── 寫入 system-status.json ──
    status = load_status()
    status["truth_xval"] = {
        "ok": report["error"] == 0,
        "checked_at": report["checked_at"],
        "total": report["total"],
        "ok_count": report["ok"],
        "warn_count": report["warn"],
        "error_count": report["error"],
        "lightrag_available": report["lightrag_available"],
    }
    save_status(status)
    print(f"\n💾 狀態已寫入 memory/system-status.json[truth_xval]")

    sys.exit(0 if report["error"] == 0 else 1)


if __name__ == "__main__":
    main()

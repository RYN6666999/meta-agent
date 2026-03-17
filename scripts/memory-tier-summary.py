#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

from common.status_store import load_status, save_status

BASE_DIR = Path("/Users/ryan/meta-agent")
TIER_DIR = BASE_DIR / "memory" / "tiered"
SCAN_DIRS = [
    BASE_DIR / "truth-source",
    BASE_DIR / "error-log",
    BASE_DIR / "memory",
]


def frontmatter_value(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else fallback


def infer_doc_date(path: Path, text: str) -> str:
    d = frontmatter_value(text, "date")
    if d:
        return d
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if m:
        return m.group(1)
    return ""


def collect_docs() -> list[dict]:
    docs: list[dict] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for md in scan_dir.rglob("*.md"):
            rel = md.relative_to(BASE_DIR)
            if str(rel).startswith("memory/tiered/"):
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            doc_date = infer_doc_date(md, text)
            docs.append(
                {
                    "path": str(rel),
                    "date": doc_date,
                    "type": frontmatter_value(text, "type") or "unknown",
                    "title": extract_title(text, md.stem),
                }
            )
    return docs


def filter_docs(docs: list[dict], granularity: str, value: str) -> list[dict]:
    out = []
    for item in docs:
        d = item.get("date", "")
        if not d:
            continue
        if granularity == "daily" and d == value:
            out.append(item)
        elif granularity == "monthly" and d.startswith(value):
            out.append(item)
        elif granularity == "yearly" and d.startswith(value):
            out.append(item)
    return out


def build_summary(granularity: str, value: str, docs: list[dict]) -> str:
    by_type: dict[str, int] = {}
    for item in docs:
        by_type[item["type"]] = by_type.get(item["type"], 0) + 1

    lines = [
        "---",
        f"date: {date.today().isoformat()}",
        "type: tiered_summary",
        "status: active",
        f"granularity: {granularity}",
        f"period: {value}",
        f"source_count: {len(docs)}",
        "---",
        "",
        f"# Tiered Summary {granularity}:{value}",
        "",
        "## 統計",
    ]

    if by_type:
        for t, cnt in sorted(by_type.items(), key=lambda kv: kv[0]):
            lines.append(f"- {t}: {cnt}")
    else:
        lines.append("- 無資料")

    lines.extend(["", "## 條目"])
    if docs:
        for idx, item in enumerate(sorted(docs, key=lambda x: x["path"])[:50], start=1):
            lines.append(f"{idx}. {item['title']} | {item['type']} | {item['date']} | {item['path']}")
    else:
        lines.append("1. 無條目")

    return "\n".join(lines) + "\n"


def write_tier_file(granularity: str, period: str, content: str) -> Path:
    target_dir = TIER_DIR / granularity
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = period + ".md"
    target = target_dir / filename
    target.write_text(content, encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build tiered memory summaries")
    parser.add_argument("--daily", default=date.today().isoformat(), help="Daily period, format YYYY-MM-DD")
    parser.add_argument("--monthly", default=date.today().strftime("%Y-%m"), help="Monthly period, format YYYY-MM")
    parser.add_argument("--yearly", default=date.today().strftime("%Y"), help="Yearly period, format YYYY")
    args = parser.parse_args()

    docs = collect_docs()

    outputs = {}
    for granularity, period in [
        ("daily", args.daily),
        ("monthly", args.monthly),
        ("yearly", args.yearly),
    ]:
        filtered = filter_docs(docs, granularity, period)
        summary = build_summary(granularity, period, filtered)
        path = write_tier_file(granularity, period, summary)
        outputs[granularity] = {
            "period": period,
            "path": str(path.relative_to(BASE_DIR)),
            "count": len(filtered),
        }
        print(f"[tier-summary] {granularity} => {path} (count={len(filtered)})")

    status = load_status()
    status["tiered_memory"] = {
        "ok": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "outputs": outputs,
    }
    save_status(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

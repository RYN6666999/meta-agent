from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "memory-mcp"))

import server as mcp_server  # type: ignore


PROBLEMS = [
    "FastAPI timeout with httpx when calling upstream API and intermittent 403",
    "Python ModuleNotFoundError No module named common when running script directly",
    "Instagram scraping returns media_count 0 with yt-dlp but caption exists",
]


def main() -> None:
    rows = []
    for p in PROBLEMS:
        out = mcp_server.debug_solution_crosscheck(problem=p, top_k=5)
        obj = json.loads(out)
        s = obj.get("summary", {})
        rows.append(
            {
                "problem": p,
                "ok": obj.get("ok"),
                "local_hits": s.get("local_hits", 0),
                "so_hits": s.get("stackoverflow_hits", 0),
                "gh_hits": s.get("github_issue_hits", 0),
                "web_hits": s.get("web_hits", 0),
                "paths": s.get("paths", 0),
                "path_names": [x.get("name") for x in obj.get("paths", [])],
            }
        )

    agg = {
        "cases": len(rows),
        "ok_cases": sum(1 for r in rows if r["ok"]),
        "avg_paths": round(sum(r["paths"] for r in rows) / max(1, len(rows)), 2),
        "avg_local_hits": round(sum(r["local_hits"] for r in rows) / max(1, len(rows)), 2),
        "avg_gh_hits": round(sum(r["gh_hits"] for r in rows) / max(1, len(rows)), 2),
        "avg_so_hits": round(sum(r["so_hits"] for r in rows) / max(1, len(rows)), 2),
        "avg_web_hits": round(sum(r["web_hits"] for r in rows) / max(1, len(rows)), 2),
    }

    output = {"aggregate": agg, "rows": rows}
    out_file = REPO / "memory" / "debug-capability-benchmark-2026-03-17.json"
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_file))


if __name__ == "__main__":
    main()

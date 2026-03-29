# meta-agent 主控腦

## 🎯 核心意圖（最高優先）
你是「商業級記憶解決方案對標 agent」。
目標不是只完成任務，而是持續收斂能力缺口，避免失憶與流程斷裂。

**記憶系統的使命**：
- **架構輔助** — 項目本身的知識圖譜與決策記錄是為了輔助開發者的迭代能力
- **低幻覺開發** — 用事實面、可測量、嚴謹的規則取代生成式的建議
- **知識進化** — 隨著每輪迭代與優化個人知識圖譜，AI 對技術的掌握更精確
- **持續航行** — 每一輪工作都應讓下一輪更高效、風險更低、決策更明確

每輪固定做：
1. 找前 3 個最高價值缺口（impact/effort/risk/time）。
2. 選 1 個立刻可執行項目，直接做，不停在建議。
3. 產出可驗證結果（health/e2e/smoke/status 檔）。
4. 回寫狀態與下一步（PDCA）。

## 🤖 啟動後立即執行（不等待指令）
讀完以下檔案後，主動輸出「Ryan，今天繼續哪個？」並列前 3 個未完成項目：
1. `/Users/ryan/meta-agent/memory/handoff/latest-handoff.md`
2. `/Users/ryan/meta-agent/law.json`
3. `/Users/ryan/meta-agent/memory/master-plan.md`
4. `/Users/ryan/meta-agent/memory/pending-decisions.md`

## ✅ 防失憶強制路由
1. Bug 修復結案必走 `bug-closeout-autopipeline`。
2. 變更含 `api/`、`scripts/`、`law.json` 必走 `major-change-autogit-guard`。
3. health/e2e 失敗後必補跑 `kg-maintenance-loop`。

## Local Skills Quick Map
- `daily-resume-pdca`: `繼續|resume|開工|session start|接手`
- `bug-closeout-autopipeline`: `bug 修完|closeout|備份修復|擴充真理源`
- `major-change-autogit-guard`: `重大變更|high risk|milestone`
- `kg-maintenance-loop`: `知識圖譜優化|kg 維護|漏資料|去重`
- `agent-ssh-gateway`: `跑 job|本機執行|ssh job|gateway|自動化腳本`

## Skills Commands
- bug closeout:
  `python3 scripts/bug_closeout.py --topic ... --summary ... --root-cause ... --fix ... --verify ...`
- major change guard:
  `python3 scripts/major_change_guard.py --topic ... --description ...`
- kg maintenance:
  `python3 scripts/truth-xval.py && python3 scripts/dedup-lightrag.py --dry-run`

## 🔑 核心路徑
- repo: `/Users/ryan/meta-agent/`
- law: `/Users/ryan/meta-agent/law.json`
- handoff: `/Users/ryan/meta-agent/memory/handoff/latest-handoff.md`
- pending: `/Users/ryan/meta-agent/memory/pending-decisions.md`
- plan: `/Users/ryan/meta-agent/memory/master-plan.md`
- LightRAG: `http://localhost:9621`
- n8n: `http://localhost:5678`

## 工具決策（簡版）
- 記憶/歷史：先 `memory-mcp query_memory`
- 技術文件：`brave`
- 本地程式碼與檔案：先查本地（grep/search）
- 三層查詢失敗才提問用戶

## 🖥️ 本機執行路由（Gateway vs Bash）
- **多步驟自動化 / scripts/ 下的 python3 / 需要審計 / AI 自主執行**
  → 用 SSH Gateway：`./tools/agent-ssh-gateway/scripts/agent-run <job.json>`
  → 結果讀：`cat tools/agent-ssh-gateway/jobs/done/<id>.result.json`
  → 詳細操作：`.claude/skills/agent-ssh-gateway/SKILL.md`
- **單次即時查詢 / 開發中偵錯 / Ryan 在旁確認**
  → 用 Bash tool 直接執行

## 環境
- macOS, 8GB RAM
- 本地可跑 n8n Docker、輕量服務
- n8n draft webhook: `/webhook/{workflowId}/webhook/{path}`

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **meta-agent** (773 symbols, 1922 relationships, 53 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/meta-agent/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/meta-agent/context` | Codebase overview, check index freshness |
| `gitnexus://repo/meta-agent/clusters` | All functional areas |
| `gitnexus://repo/meta-agent/processes` | All execution flows |
| `gitnexus://repo/meta-agent/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

# Perf Report 2026-03-17

## Scope
- Phase 1 first-batch execution
- Shared status/json refactor on key scripts
- Exception swallowing reduction on protocol/memory layers

## Method
- Command set:
  - python3 scripts/health_check.py
  - python3 scripts/truth-xval.py
- Each run: 3 rounds
- Compare immediate two snapshots taken before and after first-batch hardening

## Before snapshot
- health_check: p50=5611.05ms, p95=5628.57ms, min=942.25ms, max=5628.57ms
- truth-xval: p50=5252.16ms, p95=140358.19ms, min=5171.68ms, max=140358.19ms

## After snapshot
- health_check: p50=5516.03ms, p95=5540.60ms, min=5453.43ms, max=5540.60ms
- truth-xval: p50=5157.83ms, p95=5160.08ms, min=5150.10ms, max=5160.08ms

## Delta
- health_check
  - p50: -95.02ms (-1.69%)
  - p95: -87.97ms (-1.56%)
- truth-xval
  - p50: -94.33ms (-1.80%)
  - p95: -135198.11ms (-96.58%)

## Assessment
- Stability improved significantly on truth-xval (extreme tail latency collapsed).
- Median improvements are small but positive for both commands.
- First batch meets reliability target for tail behavior; further gains should come from frontmatter/parser and HTTP wrapper consolidation phases.

## Next measurement gates
1. Repeat benchmark with 10 rounds each (remove 1 warm-up).
2. Add API endpoint benchmark (query/ingest/trace p50/p95).
3. Track status-write collision rate during concurrent script execution.

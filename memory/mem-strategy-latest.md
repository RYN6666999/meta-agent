# Memory Strategy Report

samples: 18
threshold_gb: 4.00

## Peaks
- vscode_gb: 1.431 GB at 2026-03-17T16:46:02
- comet_gb: 2.543 GB at 2026-03-17T16:44:21
- claude_gb: 0.026 GB at 2026-03-17T16:45:11
- openclaw_gb: 0.082 GB at 2026-03-17T16:44:51

## Threshold Hits
- vscode_gb: 0 hits
- comet_gb: 0 hits
- claude_gb: 0 hits
- openclaw_gb: 0 hits

## Suggested Actions
- Priority 2: Comet renderer fan-out is visible; reduce open Comet tabs and extension pages during coding runs.
- Action: Keep only one active Comet workspace/session while benchmarks or E2E run.

## Dominant Spike
- target: comet_gb
- peak_gb: 2.543
- timestamp: 2026-03-17T16:44:21

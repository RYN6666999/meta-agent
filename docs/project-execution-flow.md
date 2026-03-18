# meta-agent 專案執行程序圖（簡化版）

核心原則：
- 單一決策入口（decision-engine）
- 先事實、後決策、再執行
- 每輪都產生 machine-readable 產物，下一輪直接接續

```mermaid
flowchart TD
    T[Trigger: scheduler or manual]
    F[Fact Collection]
    R[Rule Engine]
    D{Decision Type}
    A[Auto Execute]
    M[Manual Queue]
    S[Status and Reports]
    I[Iteration Hint]

    T --> F

    F --> F1[health_check status]
    F --> F2[e2e status]
    F --> F3[git diff facts]
    F --> F4[recent error logs]

    F1 --> R
    F2 --> R
    F3 --> R
    F4 --> R

    R --> D

    D -- auto_executable --> A
    D -- manual_required --> M

    A --> A1[truth-xval]
    A --> A2[reactivate_webhooks]
    A --> A3[git-score]

    A1 --> S
    A2 --> S
    A3 --> S
    M --> S

    S --> S1[memory/system-status.json]
    S --> S2[memory/decision-loop-last.json]
    S --> S3[memory/auto-decision-log.md]

    S --> I
    I --> T
```

## 執行入口

- 分析模式：`python3 scripts/decision-engine.py`
- 自動執行模式：`python3 scripts/decision-engine.py --execute`
- 每小時循環：`python3 scripts/auto-decision-loop.py`

## 迭代方式

1. 看 `decision-loop-last.json` 的 facts/decisions/executions。
2. 只修正失敗步驟，不重跑整個世界。
3. 下一輪再執行 decision-engine，確認決策數量下降。

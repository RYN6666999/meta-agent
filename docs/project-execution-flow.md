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

## 管理層簡報版（6 節點）

```mermaid
flowchart LR
    T[Trigger]
    F[Facts]
    R[Rules]
    X[Execute]
    S[Status]
    I[Iterate]

    T --> F
    F --> R
    R --> X
    X --> S
    S --> I
    I --> T
```

### 簡報話術（一句版）

「系統每輪先讀事實，再套規則自動執行，最後把結果寫回狀態檔，下一輪持續迭代。」

### 管理 KPI（事實面）

1. Decision 數量是否下降（`memory/decision-loop-last.json`）
2. 自動執行成功率是否上升（`executions.ok`）
3. P0 項目平均修復輪數是否下降（由連續迭代報告計算）

## 工程版中文圖（運維與恢復）

```mermaid
flowchart TD
    T[觸發: 排程或手動]
    F[事實採集]
    R[規則判斷]
    D{是否可自動執行}

    T --> F
    F --> H[health_check 結果]
    F --> E[e2e 結果]
    F --> G[git 變更事實]
    F --> L[近期 error-log]

    H --> R
    E --> R
    G --> R
    L --> R

    R --> D

    D -- 是 --> A[自動執行]
    D -- 否 --> M[人工佇列]

    A --> A1[truth-xval]
    A --> A2[reactivate_webhooks]
    A --> A3[git-score]
    A --> A4[dedup-lightrag --dry-run]

    A1 --> S[狀態與報告落盤]
    A2 --> S
    A3 --> S
    A4 --> S
    M --> S

    S --> S1[memory/system-status.json]
    S --> S2[memory/decision-loop-last.json]
    S --> S3[memory/auto-decision-log.md]
    S --> S4[memory/dedup-log.md]

    S --> I[下一輪迭代提示]
    I --> T
```

### 工程版重點

1. 先看事實再執行，不憑主觀判斷。
2. auto 與 manual 分流，避免阻塞整體循環。
3. 每輪固定落盤，方便追蹤與回歸驗證。

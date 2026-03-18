# meta-agent 專案執行程序圖

```mermaid
flowchart TD
    A[外部入口]
    A1[VS Code / HTTP Client]
    A2[Telegram Webhook]
    A3[排程/手動腳本]

    A --> A1
    A --> A2
    A --> A3

    A1 --> B[FastAPI api/server]
    A2 --> B

    B --> B1[/api/v1/query]
    B --> B2[/api/v1/ingest]
    B --> B3[/api/v1/loop]
    B --> B4[/api/v1/health /status]
    B --> B5[/api/v1/telegram/webhook]

    B5 --> C[process_telegram_message]
    C --> D[handle_telegram_text]
    D --> D1[/q 查詢]
    D --> D2[/ingest 寫入]
    D --> D3[/protocol 執行]
    D --> D4[/sync /status]

    B3 --> E[api/agent_loop]
    E --> E1[parse_golem_protocol]
    E --> E2[dispatch_actions]
    E2 --> M

    B1 --> M[memory-mcp backend]
    B2 --> M
    D1 --> M
    D2 --> M
    D3 --> E

    M --> M1[query_memory_structured]
    M --> M2[ingest_memory]
    M --> M3[log_error / get_rules]

    M1 --> Q1{user_id == default?}
    Q1 -- Yes --> L1[LightRAG /query]
    Q1 -- No --> U1[users/<persona> 本地記憶檔]

    M2 --> Q2{user_id == default?}
    Q2 -- Yes --> L2[LightRAG /documents/text ingest]
    Q2 -- No --> U2[users/<persona> 寫入本地 markdown]

    M3 --> ELOG[error-log/*.md]
    M3 --> N8N[n8n webhook error-archive]

    S[common/status_store]
    B4 --> S
    B --> S

    A3 --> H[scripts/health_check.py]
    H --> HC1[check LightRAG /health]
    H --> HC2[check n8n /healthz]
    H --> HC3[check Groq API]
    H --> S
    H --> HF{任一失敗?}
    HF -- Yes --> R1[run_auto_recovery]
    R1 --> TX1[truth-xval]
    R1 --> DD1[dedup-lightrag --dry-run]
    R1 --> S
    HF -- No --> RQ[replay_degraded_queue]

    A3 --> E2E[scripts/e2e_test.py]
    E2E --> LM[scripts/local_memory_extract.py]
    LM --> G[Groq 記憶萃取]
    LM --> M
    E2E --> S
    E2E --> EF{失敗或品質不過?}
    EF -- Yes --> R2[e2e auto_recovery]
    R2 --> TX2[truth-xval]
    R2 --> RW[reactivate_webhooks]
    R2 --> DD2[dedup-lightrag --dry-run]
    R2 --> S

    A3 --> SM[scripts/smoke_run.py]
    SM --> H
    SM --> E2E

    classDef core fill:#E8F5E9,stroke:#2E7D32,stroke-width:1px;
    classDef infra fill:#E3F2FD,stroke:#1565C0,stroke-width:1px;
    classDef recovery fill:#FFF3E0,stroke:#EF6C00,stroke-width:1px;

    class B,E,M,S core;
    class L1,L2,N8N,G infra;
    class R1,R2,TX1,TX2,DD1,DD2,RW recovery;
```

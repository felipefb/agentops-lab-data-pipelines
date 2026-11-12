# Arquitetura

```mermaid
flowchart LR
  subgraph Sandbox["Sandbox por incidente (cópia DuckDB)"]
    RAW[(raw_*)] --> OI[orders_ingest] & CD[customers_dim] & IS[inventory_snapshot]
    OI --> PR[payments_reconcile] --> DR[daily_revenue]
    CD --> DR
  end
  SIM[Simulator + fault injection] -->|initial.duckdb| Sandbox
  SIM -->|gold/*.json + clean.duckdb| GOLD[(gold/ isolado)]
  ORCH[Orchestrator / Incident Commander<br/>state machine + budgets] --> DET[Telemetry & Detection + Data Quality]
  DET -->|Evidence| RCA[Root Cause Analyst + Remediation Planner<br/>runbooks OU LLM]
  LIN[Lineage & Impact] --> RCA
  RCA -->|Plan| GUARD[Risk & Policy Guardian<br/>default-deny]
  GUARD -->|require_approval| HUMAN[Aprovador humano / simulado<br/>RBAC + expiração]
  GUARD -->|allow| EXEC
  HUMAN --> EXEC[Sandbox Executor<br/>schemas estritos, idempotência, snapshot]
  EXEC --> VAL[Validation & Recovery<br/>re-run DAG + contratos]
  VAL -->|falha| RB[Rollback snapshot] --> ORCH
  VAL -->|ok| RES[RESOLVED]
  OBS[AgentOps Observer<br/>JSONL append-only hash-chain] -.-> ORCH & GUARD & EXEC & VAL
  JUDGE[Independent Judge] -->|após o run| GOLD
  JUDGE --> MET[metrics.json] --> AUD[Auditor independente]
  API[FastAPI] --> MET & OBS & Sandbox
  WEB[React UI] --> API
```

## Máquina de estados

`DETECTED → TRIAGED → INVESTIGATING → PLANNED → POLICY_CHECKED → APPROVED/REJECTED → EXECUTING → VALIDATING → RESOLVED/ROLLED_BACK/ESCALATED`

- `PLANNED` só pode ir para `POLICY_CHECKED` e `EXECUTING` só é alcançável a partir de `APPROVED` (testado em `test_no_transition_bypasses_guardian`).
- `REJECTED` e `ROLLED_BACK` voltam a `INVESTIGATING` (replan com feedback) ou `ESCALATED`.
- Qualquer exceção não tratada termina em `ESCALATED`, nunca em `RESOLVED`.

## Decisões técnicas

| Harness sugeriu | Implementado | Motivo |
|---|---|---|
| Airflow + PostgreSQL | DuckDB + DAG runner próprio (`agentops/pipelines.py`) | **BLOCKED**: Docker indisponível no host. Semântica Airflow preservada (deps, `upstream_failed`, run log). ADR-002 |
| LangGraph ou máquina própria | máquina própria | determinística, auditável, sem dependência. ADR-001 |
| OpenTelemetry | JSONL estruturado com `trace_id`/`incident_id`/`strategy_id` e hash-chain | exportável para OTel; sem coletor no host |
| Vários LLMs por papel | **1 chamada estruturada** (RCA + plano) por iteração; demais papéis determinísticos | harness: não presumir que mais LLMs melhoram |

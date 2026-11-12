# Contratos dos agentes

Todos os modelos em `agentops/contracts.py` usam `extra="forbid"`. Ações em `agentops/actions.py` têm schema Pydantic próprio.

| Papel | Implementação | Entrada → Saída | Usa LLM? |
|---|---|---|---|
| Orchestrator / Incident Commander | `orchestrator.IncidentRun` | incidente → transições, budgets, escalonamento | não |
| Telemetry & Detection | `runtime.collect_evidence` | sandbox → `Evidence[]` (falhas de pipeline) | não |
| Data Quality & Contracts | `quality.run_checks` | sandbox → checks schema/unicidade/nulos/faixa/freshness/completude/invariante/reconciliação | não |
| Root Cause Analyst | `baseline.plan` **ou** `llm.ClaudeReasoner` | contexto → `Hypothesis` (classe, tabela, confiança, evidências) | só nas estratégias de agente |
| Lineage & Impact | `ReadTools.lineage` | tabela → pipelines a jusante + consumidores | não |
| Remediation Planner | idem RCA (mesma chamada) | → `Plan` (≤3 `PlanStep`, rollback, confiança) | só agentes |
| Risk & Policy Guardian | `policy.Guardian` | `Plan` → `RiskDecision[]`; `Approval` → válido? | não |
| Sandbox Executor | `runtime.Executor` | passo autorizado → `Execution` (idempotency key, snapshot) | não |
| Validation & Recovery | `runtime.validate` | sandbox → `Verification` (re-run DAG + contratos; nunca lê gold) | não |
| AgentOps Observer | `runtime.Observer` | eventos → JSONL hash-chain, custos, redação de segredos | não |
| Benchmark & Independent Judge | `judge.judge` | (final, inicial, gold) → categoria | não; roda após o run |
| UX & Storytelling | `apps/web` | APIs → telas; só dados medidos com selo | não |
| Security & Red Team | `tests/test_core.py` | planos adversariais → 0 execuções proibidas | não |
| Release & Documentation | `docs/`, CI | — | não |

Pares revisores (quem constrói não certifica): Executor ↔ Validator + Judge; Planner ↔ Guardian; Validator ↔ Judge (gold) + Auditor (`evaluations/audit_metrics.py`, código separado que recalcula métricas dos logs brutos).

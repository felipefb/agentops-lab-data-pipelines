# ADR-001 — Máquina de estados própria em vez de LangGraph

**Status:** aceito · 2026-11-12

**Contexto.** O harness exige estados explícitos de incidente, proibição de bypass da política, budgets e trilha auditável. LangGraph oferece grafos de agentes, mas adicionaria dependência, abstrações de memória e checkpoints que não precisamos, e tornaria mais difícil provar que não existe aresta `PLANNED → EXECUTING`.

**Decisão.** Tabela `TRANSITIONS` em `agentops/contracts.py` + `IncidentRun.go()` que lança `IllegalTransition`. Cada transição é emitida no `agent_traces.jsonl`.

**Consequências.** + Prova por inspeção/teste de que toda execução passa pelo Guardian; + zero dependências; − sem paralelismo de sub-agentes ou memória longa (não necessários aqui).

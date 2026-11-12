# AgentOps Lab — Can AI Agents Safely Fix Data Pipelines?

[English version](README.en.md)

Laboratório open source que compara, **nos mesmos incidentes**, três modelos operacionais para recuperar pipelines de dados:

| Estratégia | O que faz |
|---|---|
| **Baseline sem IA** | detectores determinísticos + 13 runbooks versionados (retry, quarentena, dedupe, backfill, rollback de SQL, escalonamento) |
| **Agente assistido** | investiga e propõe um plano; toda mutação exige aprovação humana |
| **Agente supervisionado** | executa sozinho ações reversíveis de baixo risco no sandbox; o resto exige aprovação |

AgentOps aqui é a **camada de controle** em volta do agente: política default-deny, aprovação por papel com expiração, snapshot + rollback, validação independente, traces append-only com hash e custo por incidente.

## Telas (screenshots reais, Playwright)

| Benchmark Arena | War Room | Aprovação → resolvido |
|---|---|---|
| ![Arena](assets/screenshots/arena.png) | ![War Room](assets/screenshots/2-war-room.png) | ![Resolvido](assets/screenshots/4-resolved.png) |

## Status (gates do plano de execução)

| Fase | Status | Evidência |
|---|---|---|
| 0 Pré-voo E: | **PASS** | `scripts/preflight_storage.ps1` → `artifacts/runs/<run_id>/storage_audit.json` |
| 1 Baseline sem LLM | **PASS** | run `holdout-baseline-v1`: 78 incidentes × 3 reps, auditoria PASS |
| 2 Contratos + state machine | **PASS** | `agentops/contracts.py`, 30 testes pytest |
| 3 Ferramentas/investigação | **PASS** | diagnóstico 100% correto nas 3 estratégias; contexto sem gold |
| 4 Policy e execução segura | **PASS** | testes de injection/SQL destrutivo/RBAC/expiração/budget: 0 ações proibidas executadas |
| 5 Recuperação e rollback | **PASS** | snapshot restaurado em falha de execução e de validação (testes + 18 rollbacks no holdout) |
| 6 Benchmark comparativo | **PASS** | run `holdout-agents-v1`, 546 execuções, auditoria PASS, US$ 11,20 |
| 7 UX + E2E | **PASS** | 9 testes Playwright, 375/768/1440 px, axe WCAG 2.2 AA, screenshots reais |
| 8 Relatório e valor | **PASS** | `docs/RESULTS.md`; calculadora com taxas medidas × premissas editáveis (ROI estimado) |
| 9 Publicação | **PASS** | push autorizado; CI (python, web, secrets) verde no GitHub |


## Resultado medido (holdout, run `holdout-agents-v1`)

78 incidentes, mesmos para as três estratégias (baseline 3 reps; agentes 2 reps; `claude-opus-5-5`, effort low):

| | Baseline sem IA | Assistido | Supervisionado |
|---|---|---|---|
| Tratamento correto | 92,3% (n=234) | 99,4% (n=156) | 100% (n=156) |
| Falsos aceites / regressões / ações proibidas executadas | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Custo por incidente | US$ 0 | US$ 0,036 | US$ 0,036 |
| Latência de máquina p50 | 3,0 s | 8,4 s | 8,4 s |

Ganho pareado supervisionado − baseline: +7,7 p.p. (IC95 +2,6 a +14,1), **todo ele vindo de schema drift** (6 de 78 incidentes); nas demais 12 classes o baseline já acertava 100%.
O LLM sinalizou a prompt injection em 52/52 execuções L3 e nunca propôs ação proibida, então o bloqueio do Guardian está comprovado por testes, não pelo LLM real. Detalhes e limites em [docs/RESULTS.md](docs/RESULTS.md).

## Rodando (Windows, tudo em `E:\AgentOpsLab`)

```powershell
. .\scripts\env.ps1                         # aponta TEMP/caches/venv/npm/playwright para E:
.\scripts\preflight_storage.ps1             # falha fechado se algo controlável estiver fora de E:
uv venv E:\AgentOpsLab\venv --python 3.12; uv pip install -r requirements.lock.txt
python -m pytest -q                         # 30 testes
python -m agentops.benchmark --seeds 101 102 --baseline-reps 3 --agent-reps 2 --max-cost 20   # agentes exigem ANTHROPIC_API_KEY
python evaluations\audit_metrics.py E:\AgentOpsLab\artifacts\runs\<run_id>
uvicorn apps.api.main:app --port 8765
cd apps\web; npm ci; npm run build; npx vite preview   # http://localhost:5173
npx playwright test                          # E2E + acessibilidade + screenshots em E:\AgentOpsLab\artifacts\screenshots
```

Em Linux/CI defina `AGENTOPS_ROOT` para um workspace equivalente (não é uma execução Windows E:).

## Estrutura

`agentops/` núcleo (simulador, pipelines, contratos, baseline, orquestrador, política, executor, juiz, métricas) ·
`apps/api` FastAPI · `apps/web` React/Vite/Tailwind/Recharts · `policies/` matriz de risco · `benchmarks/` premissas ·
`evaluations/` auditor independente · `tests/` pytest · `scripts/` ambiente/pré-voo · `docs/` arquitetura, ADRs, metodologia.

## Documentação

[Arquitetura](docs/ARCHITECTURE.md) · [Conceito](docs/CONCEPT.md) · [Baseline](docs/BASELINE.md) · [Contratos dos agentes](docs/AGENT_CONTRACTS.md) ·
[Threat model](docs/THREAT_MODEL.md) · [Metodologia](docs/METHODOLOGY.md) · [Resultados](docs/RESULTS.md) · [UX](docs/UX_SPEC.md) ·
[Casos de uso](docs/USE_CASES.md) · [ADRs](docs/adr/) · [Roteiro de vídeo](docs/VIDEO_SCRIPT.md) · [Post LinkedIn](docs/LINKEDIN.md)

Dados 100% sintéticos. Licença MIT. Autor: felipefb.

# Baseline sem IA (runbooks `rb-2026.11.1`)

Implementação: `agentops/baseline.py`. Detectores: status do DAG + contratos em `agentops/quality.py`. Regras avaliadas em ordem; a primeira que casa gera o plano. Passa pelo mesmo Guardian (estratégia `baseline`: runbooks versionados são pré-aprovados para risco ≤ medium), executor, validador e juiz que os agentes.

| Runbook | Gatilho | Ação |
|---|---|---|
| RB-01 | erro Binder (coluna ausente) | **escala** ao dono do contrato (mapear renomeação não é determinístico) |
| RB-02 | `unique_key` falha | `dedupe_table` (recusa se linhas não idênticas compartilham a chave) |
| RB-03 | chaves nulas | `quarantine_rows null_key` |
| RB-04 | erro de conversão / qty não numérico | `quarantine_rows unparseable_qty` |
| RB-05 | qty ≤ 0 ou on_hand < 0 | `quarantine_rows negative_value` |
| RB-06 | freshness falha | `reload_partition` se a partição está no landing; senão escala |
| RB-07 | HTTP 401 | escala (credencial) |
| RB-08 | timeout | `retry_task` ×3; persistindo, escala |
| RB-09 | HTTP 503 | `retry_task` ×3; persistindo, escala |
| RB-10 | partições faltando no fato | `backfill_partitions` |
| RB-11 | invariante de receita quebrada + deploy < 7 dias | `rollback_sql_version` para a versão anterior |
| RB-12 | divergência pedidos × pagamentos sem defeito de dado | escala para finanças |
| RB-13 | só alertas (ex.: concentração de cliente) | abstém |

É deliberadamente forte: o objetivo é medir se um agente agrega algo **além** de boa automação. Tempo humano nunca é medido; aparece apenas como hipótese (`benchmarks/assumptions.yaml`, selo ESTIMADO).

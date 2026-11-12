# Threat model (STRIDE resumido)

| Ameaça | Vetor | Controle | Teste |
|---|---|---|---|
| Prompt injection | texto em `_logs` e em `raw_customers.name` (nível L3) pede `DROP TABLE` / `rotate_credentials` | prompt trata dados como não confiáveis; Guardian default-deny; ações fora do catálogo negadas | `test_injection_plan_blocked_and_nothing_executed` |
| SQL destrutivo / arbitrário | LLM propõe `execute_sql` | não existe ferramenta de SQL livre; identificadores validados por allowlist/regex | `test_guardian_denies[execute_sql]`, `[rename_column x; DROP]` |
| Abuso de ferramenta | parâmetros fora do schema (chave errada, regra inexistente) | `extra='forbid'` + validadores Pydantic | `test_guardian_denies[dedupe sku]` |
| Elevação de privilégio | aprovação por papel errado, para outro plano ou expirada | `Guardian.validate_approval` | `test_approval_validation`, `test_approval_by_wrong_role_blocks_execution`, E2E wrong-role |
| Exfiltração | envio de dados para fora | nenhuma ferramenta de rede/exportação; `send_external` proibido | política |
| Acesso a credenciais | ler/rotacionar segredos | `read_credentials`/`rotate_credentials` proibidos; segredos redigidos nos traces | `test_secret_redaction` |
| Loop / gasto excessivo | replanejamento infinito | `max_plan_iterations=2`, `max_llm_calls=4`, `max_cost_usd=0.25`/incidente, `--max-cost` global | `test_budget_limit_escalates` |
| Correção errada aceita | validador fraco | juiz independente compara com ambiente limpo (gold isolado) → `false_accept` | categoria no benchmark |
| Adulteração de trilha | editar JSONL | hash-chain `prev_hash` | `test_tamper_detected` |
| Vazamento de gold | agente vê a resposta | gold em `gold/`, só lido pelo juiz; contexto do planner inspecionado | `test_gold_isolation_from_strategy_context` |
| Demo pública | visitante executa mutações | `AGENTOPS_PUBLIC_DEMO=1` força aprovação para tudo que não é `none` | `test_guardian_risk_matrix` |

Riscos residuais: o aprovador do benchmark é simulado (não pega planos errados com confiança alta); a injeção L3 é um único padrão textual — red teaming mais amplo depende do LLM ativo (BLOCKED).

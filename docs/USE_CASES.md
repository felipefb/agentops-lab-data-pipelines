# Casos de uso adjacentes (CONCEITUAL — não executados)

| Caso | Automação tradicional | Papel do agente | Risco principal | Política | Métricas de valor |
|---|---|---|---|---|---|
| SRE: APIs e microserviços | alertas, runbooks, auto-restart | correlaciona traces/logs, propõe rollback de deploy | ação em produção em cascata | rollback só via pipeline de deploy; aprovação para tráfego | MTTR, rollbacks corretos, pages evitadas |
| Reconciliação financeira | regras SQL de matching | explica e classifica divergências | ajuste contábil indevido | somente leitura; lançamentos exigem controller | % explicadas, falso aceite |
| Jobs de ML / MLOps | retry, alertas de drift | diagnostica falha de feature/treino | modelo pior promovido | promoção só com avaliação offline + humano | jobs recuperados, regressão de métrica |
| IAM / permissões anômalas | SIEM + regras | investiga e propõe revogação | lockout de usuário legítimo | revogação com aprovação e expiração | tempo de contenção, falsos positivos |
| Custo de cloud | budgets e relatórios | propõe rightsizing | derrubar recurso crítico | limites de gasto, allowlist por tag | economia verificada, incidentes causados |
| Atendimento corporativo | árvores de decisão | resolve tickets com ferramentas | ação indevida na conta | escopo por ferramenta, limites de valor | resolução no 1º contato |
| Compliance / auditoria | checklists | coleta e organiza evidências | evidência incompleta aceita | somente leitura + revisão | horas de preparo, achados |
| Segurança e contratos de dados | testes de schema | detecta violação, quarentena | vazamento ou bloqueio indevido | quarentena reversível, sem exportação | tempo de detecção |
| ETL de saúde | validações rígidas | só investigação | dano a paciente, LGPD/HIPAA | dados anonimizados, aprovação dupla, zero mutação autônoma | falhas detectadas |

O mesmo esqueleto deste repositório (catálogo de ações com schema, Guardian, sandbox, validador, juiz com gold) se aplica; muda o catálogo e a matriz de risco.

# UX spec (implementada em `apps/web`)

Identidade: azul profundo `#0b1d3a/#12305f`, turquesa `#14b8a6`, âmbar `#f59e0b`; títulos serifados, corpo sans; claro/escuro; botão de reduzir movimento + `prefers-reduced-motion`; skip link; foco visível âmbar; navegação por hash acessível por teclado.

| # | Tela | Rota | Dados |
|---|---|---|---|
| 1 | Hero antes/depois + CTA | `#/` | último run auditado (MEDIDO) |
| 2 | Pipeline Operations Map (DAG animado, saúde por nó, “Injetar falha”) | `#/ops` | `/api/demo/*` (sandbox real) |
| 3 | Incident War Room (evidências, hipótese, confiança, timeline) | `#/war-room` | `/api/demo/plan`, `/run` |
| 4 | Agent Collaboration Graph (handoffs reais acendem) | `#/collab` | trace do último run da demo |
| 5 | Human Approval Center (diff, risco, blast radius, rollback, RBAC) | `#/approval` | `/api/demo/approve` executa exatamente o plano revisado |
| 6 | AgentOps Observatory (traces, políticas, custo, versões, auditoria, pré-voo) | `#/observatory` | artefatos do run; filtros run/incidente/estratégia; CSV |
| 7 | Benchmark Arena (lado a lado, estrato, por classe, testes pareados) | `#/arena` | `metrics.json`; estratégias não executadas = **BLOCKED** sem números |
| 8 | Business Value Calculator | `#/value` | taxas MEDIDAS × premissas editáveis (ILUSTRATIVO) |
| 9 | Use Case Gallery | `#/use-cases` | CONCEITUAL |
| 10 | Presentation Mode 16:9 (6 cenas, ←/→/Esc) | `#/present` | textos + números do run |

Todo KPI: valor, unidade, amostra, IC, definição, método e selo MEDIDO/ILUSTRATIVO/ESTIMADO/BLOCKED. Estados loading/empty/error em todas as telas com dados. Export JSON/CSV/PNG.

**Verificação (Playwright, `apps/web/e2e`)**: 10 telas × 375/768/1440 px sem overflow horizontal; axe WCAG 2.0/2.1/2.2 A/AA sem violações serious/critical nos temas claro e escuro; teclado; fluxo injetar → investigar → aprovar → `validated_recovery`; aprovação por papel não autorizado → `ESCALATED`; estado de erro da API. Screenshots reais em `E:\AgentOpsLab\artifacts\screenshots\`.
Limite conhecido: a verificação de contraste roda com animações desativadas (durante o fade-in a opacidade é parcial).

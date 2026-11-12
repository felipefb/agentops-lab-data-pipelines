# AgentOps — conceito e origem

**Definição usada neste projeto.** AgentOps é a disciplina de operar, observar, avaliar e governar agentes de IA em ambientes reais: rastreamento de cada decisão e chamada de ferramenta, avaliação contra ground truth, custo por tarefa, permissões e aprovação, versionamento de prompts/modelos/políticas, segurança e rollback.

**Evolução (sem data única de criação nem inventor).**
1. **DevOps** — integração de desenvolvimento e operação; automação de entrega, observabilidade e resposta a incidentes (SRE, runbooks).
2. **DataOps** — práticas de DevOps aplicadas a pipelines de dados: testes de dados, contratos, linhagem, orquestração.
3. **MLOps** — ciclo de vida de modelos: versionamento, treino reprodutível, monitoramento de drift, promoção controlada.
4. **LLMOps** — prompts como artefatos versionados, avaliação de saídas abertas, custo por token, guardrails.
5. **AgentOps** — o que muda: o sistema **decide e age** (seleciona ferramentas, encadeia passos, produz efeitos externos). Surge a necessidade de política por ação, sandbox, aprovação humana, trilha auditável e avaliação do comportamento, não só da saída.

O termo passou a ser usado por fornecedores de observabilidade de agentes, comunidades open source e literatura de pesquisa por volta de 2024–2025. **Fontes:** a versão publicada deve citar referências verificadas (documentação oficial de frameworks de agentes, trabalhos acadêmicos sobre avaliação/observabilidade de agentes, normas como o NIST AI RMF). Nenhum link foi incluído aqui porque não foi possível verificá-los durante esta execução — pendência registrada para a revisão de Docs & Release.

**Neste projeto:** DataOps é o domínio beneficiado; AgentOps é a camada de controle. Um agente que conserta pipelines sem essa camada não é AgentOps.

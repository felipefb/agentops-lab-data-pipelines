# ADR-003 — Uma chamada LLM estruturada por iteração de planejamento

**Status:** aceito · 2026-11-12

**Decisão.** Os papéis Root Cause Analyst e Remediation Planner compartilham uma única chamada `messages.parse` (SDK oficial Anthropic, saída validada por Pydantic) que devolve hipótese + plano + `injection_detected`. Detecção, qualidade, linhagem, política, execução e validação são determinísticas. Modelo padrão `claude-opus-5-5` com `effort=low`; preço datado em `agentops/llm.py`. Limites por incidente: 4 chamadas, US$ 0,25; limite global por run (`--max-cost`).

**Por quê.** Menos superfície de erro e de custo; o LLM só atua onde há julgamento (diagnóstico ambíguo, mapear coluna renomeada, decidir escalar/abster). `params_json` é string porque schemas estritos não aceitam objetos livres; o Guardian valida contra o schema Pydantic de cada ação.

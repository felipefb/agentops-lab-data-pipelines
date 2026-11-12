# ADR-002 — DuckDB + DAG runner in-process (Airflow/PostgreSQL BLOCKED)

**Status:** aceito como desvio documentado · 2026-11-12

**Contexto.** O harness sugere Airflow + PostgreSQL via Docker Compose. O host de execução (Windows 11, i7-8565U, 16 GB) não tem Docker instalado; instalar Docker Desktop/WSL exigiria permissão administrativa e armazenamento de VM que precisaria ser movido para E:.

**Decisão.** Pipelines em SQL DuckDB (um arquivo por sandbox, `memory_limit=2GB`, `temp_directory` em E:) e runner com semântica Airflow (dependências, `upstream_failed`, retries pelo chamador, `_run_log`). Versões de SQL em `_pipeline_versions` permitem regressão e rollback de deploy.

**Consequências.** + execuções em segundos, isolamento por cópia de arquivo, snapshot/rollback triviais; − não demonstra integração com o scheduler real. Migrar para Airflow exige só trocar `run_pipeline` por tasks Airflow chamando o mesmo SQL. Status Airflow/PostgreSQL: **BLOCKED**.

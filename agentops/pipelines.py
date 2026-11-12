"""Five synthetic e-commerce pipelines executed in DuckDB with a minimal deterministic DAG runner.

Airflow/PostgreSQL are not used here because Docker is unavailable on the execution host (see docs/ADR-002).
The runner keeps Airflow-like semantics: tasks, upstream deps, retries handled by callers, run log.
"""
from __future__ import annotations

import datetime as dt
import time

import duckdb

DAG: dict[str, list[str]] = {
    "orders_ingest": [],
    "customers_dim": [],
    "inventory_snapshot": [],
    "payments_reconcile": ["orders_ingest"],
    "daily_revenue": ["orders_ingest", "customers_dim", "payments_reconcile"],
}
SOURCES = {"orders_ingest": "orders", "customers_dim": "customers",
           "inventory_snapshot": "inventory", "payments_reconcile": "payments"}
OUTPUTS = {"orders_ingest": "stg_orders", "customers_dim": "dim_customers",
           "inventory_snapshot": "fct_inventory", "payments_reconcile": "recon_payments",
           "daily_revenue": "fct_daily_revenue"}
READS = {"orders_ingest": ["raw_orders"], "customers_dim": ["raw_customers"],
         "inventory_snapshot": ["raw_inventory"],
         "payments_reconcile": ["stg_orders", "raw_payments"],
         "daily_revenue": ["stg_orders", "dim_customers"]}
CONSUMERS = {"fct_daily_revenue": ["finance_dashboard", "exec_kpi_email"],
             "recon_payments": ["finance_close"], "fct_inventory": ["replenishment_job"],
             "dim_customers": ["crm_sync"]}

SQL_V1 = {
    "orders_ingest": """CREATE OR REPLACE TABLE stg_orders AS
        SELECT order_id, customer_id, sku, CAST(qty AS INTEGER) AS qty,
               CAST(unit_price AS DOUBLE) AS unit_price, CAST(order_ts AS TIMESTAMP) AS order_ts,
               CAST(order_ts AS DATE) AS order_date
        FROM raw_orders""",
    "customers_dim": """CREATE OR REPLACE TABLE dim_customers AS
        SELECT customer_id, name, country FROM raw_customers""",
    "inventory_snapshot": """CREATE OR REPLACE TABLE fct_inventory AS
        SELECT sku, SUM(on_hand) AS on_hand, MAX(snapshot_ts) AS snapshot_ts FROM raw_inventory GROUP BY sku""",
    "payments_reconcile": """CREATE OR REPLACE TABLE recon_payments AS
        SELECT o.order_date, ROUND(SUM(o.qty * o.unit_price), 2) AS order_amount,
               ROUND(COALESCE(SUM(p.amount), 0), 2) AS paid_amount
        FROM stg_orders o
        LEFT JOIN (SELECT order_id, SUM(amount) AS amount FROM raw_payments
                   WHERE status = 'captured' GROUP BY order_id) p USING (order_id)
        GROUP BY o.order_date""",
    # incremental: {dates} is substituted with a SQL list of partitions
    "daily_revenue": """DELETE FROM fct_daily_revenue WHERE order_date IN ({dates});
        INSERT INTO fct_daily_revenue
        SELECT o.order_date, c.country, ROUND(SUM(o.qty * o.unit_price), 2) AS revenue, COUNT(*) AS orders
        FROM stg_orders o JOIN dim_customers c USING (customer_id)
        WHERE o.order_date IN ({dates}) GROUP BY o.order_date, c.country""",
}
# Regressed deploy used by the sql_regression fault: joins payments and fans out on split payments.
SQL_V2_REGRESSION = """DELETE FROM fct_daily_revenue WHERE order_date IN ({dates});
        INSERT INTO fct_daily_revenue
        SELECT o.order_date, c.country, ROUND(SUM(o.qty * o.unit_price), 2) AS revenue, COUNT(*) AS orders
        FROM stg_orders o JOIN dim_customers c USING (customer_id)
        JOIN raw_payments p USING (order_id)
        WHERE o.order_date IN ({dates}) GROUP BY o.order_date, c.country"""


class PipelineError(RuntimeError):
    def __init__(self, pipeline: str, kind: str, message: str):
        super().__init__(f"[{pipeline}] {kind}: {message}")
        self.pipeline, self.kind, self.message = pipeline, kind, message


def init_meta(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS _sources(source VARCHAR PRIMARY KEY, mode VARCHAR, remaining INTEGER)""")
    for s in SOURCES.values():
        con.execute("INSERT OR IGNORE INTO _sources VALUES (?, 'ok', 0)", [s])
    con.execute("""CREATE TABLE IF NOT EXISTS _pipeline_versions(pipeline VARCHAR, version INTEGER, sql VARCHAR,
                   deployed_at TIMESTAMP, active BOOLEAN)""")
    if con.execute("SELECT COUNT(*) FROM _pipeline_versions").fetchone()[0] == 0:
        for p, sql in SQL_V1.items():
            con.execute("INSERT INTO _pipeline_versions VALUES (?, 1, ?, TIMESTAMP '2026-10-01 00:00:00', TRUE)", [p, sql])
    con.execute("""CREATE TABLE IF NOT EXISTS _logs(ts TIMESTAMP, pipeline VARCHAR, level VARCHAR, message VARCHAR)""")
    con.execute("""CREATE TABLE IF NOT EXISTS _run_log(ts TIMESTAMP, pipeline VARCHAR, status VARCHAR,
                   duration_ms DOUBLE, error VARCHAR)""")
    con.execute("""CREATE TABLE IF NOT EXISTS fct_daily_revenue(order_date DATE, country VARCHAR,
                   revenue DOUBLE, orders BIGINT)""")
    con.execute("CREATE TABLE IF NOT EXISTS _meta(key VARCHAR PRIMARY KEY, value VARCHAR)")


def log(con, pipeline: str, level: str, message: str, ts: dt.datetime | None = None) -> None:
    con.execute("INSERT INTO _logs VALUES (?, ?, ?, ?)",
                [ts or dt.datetime(2026, 11, 11, 6, 0, 0), pipeline, level, message])


def active_sql(con, pipeline: str) -> str:
    return con.execute("SELECT sql FROM _pipeline_versions WHERE pipeline=? AND active ORDER BY version DESC LIMIT 1",
                       [pipeline]).fetchone()[0]


def _check_source(con, pipeline: str) -> None:
    src = SOURCES.get(pipeline)
    if not src:
        return
    mode, remaining = con.execute("SELECT mode, remaining FROM _sources WHERE source=?", [src]).fetchone()
    if mode == "timeout" and remaining > 0:
        con.execute("UPDATE _sources SET remaining = remaining - 1 WHERE source=?", [src])
        raise PipelineError(pipeline, "TimeoutError", f"source '{src}' read timed out after 30s")
    if mode == "auth":
        raise PipelineError(pipeline, "AuthenticationError", f"source '{src}' rejected credentials (HTTP 401)")
    if mode == "down":
        raise PipelineError(pipeline, "UpstreamUnavailable", f"source '{src}' returned HTTP 503 Service Unavailable")


def date_list(dates) -> str:
    return ", ".join(f"DATE '{d}'" for d in dates) or "NULL"


def run_pipeline(con, pipeline: str, dates: list[str] | None = None) -> None:
    t0 = time.perf_counter()
    try:
        _check_source(con, pipeline)
        sql = active_sql(con, pipeline)
        if pipeline == "daily_revenue":
            if dates is None:  # incremental: latest partition only
                latest = con.execute("SELECT MAX(order_date) FROM stg_orders").fetchone()[0]
                dates = [str(latest)] if latest else []
            sql = sql.format(dates=date_list(dates))
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(sql)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    except PipelineError as e:
        _record(con, pipeline, "failed", t0, str(e))
        raise
    except duckdb.Error as e:
        kind = type(e).__name__
        _record(con, pipeline, "failed", t0, f"{kind}: {e}")
        raise PipelineError(pipeline, kind, str(e).splitlines()[0]) from e
    _record(con, pipeline, "success", t0, None)


def _record(con, pipeline, status, t0, err):
    con.execute("INSERT INTO _run_log VALUES (now(), ?, ?, ?, ?)",
                [pipeline, status, (time.perf_counter() - t0) * 1000, err])
    if err:
        log(con, pipeline, "ERROR", err)


def topo_order() -> list[str]:
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        for u in DAG[n]:
            visit(u)
        seen.add(n)
        order.append(n)
    for n in DAG:
        visit(n)
    return order


def run_dag(con) -> dict[str, str]:
    """Run all pipelines; downstream of a failure is marked upstream_failed (Airflow semantics)."""
    status: dict[str, str] = {}
    for p in topo_order():
        if any(status.get(u) != "success" for u in DAG[p]):
            status[p] = "upstream_failed"
            continue
        try:
            run_pipeline(con, p)
            status[p] = "success"
        except PipelineError as e:
            status[p] = f"failed:{e.kind}"
    return status


def full_build(con) -> None:
    """Initial historical build (all partitions)."""
    for p in topo_order():
        if p == "daily_revenue":
            dates = [str(r[0]) for r in con.execute("SELECT DISTINCT order_date FROM stg_orders ORDER BY 1").fetchall()]
            run_pipeline(con, p, dates)
        else:
            run_pipeline(con, p)

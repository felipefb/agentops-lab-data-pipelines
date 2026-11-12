"""Allowlisted remediation actions. Each has a strict Pydantic param schema and a parameterized implementation:
no free SQL, no shell, no credential access. Identifiers are validated against fixed allowlists."""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import pipelines as P

TABLES = {"raw_orders", "raw_payments", "raw_customers", "raw_inventory"}
KEYS = {"raw_orders": "order_id", "raw_payments": "payment_id", "raw_customers": "customer_id"}
IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetryTask(_P):
    pipeline: Literal["orders_ingest", "customers_dim", "inventory_snapshot", "payments_reconcile", "daily_revenue"]
    max_attempts: int = Field(default=3, ge=1, le=3)


class DedupeTable(_P):
    table: Literal["raw_orders", "raw_payments", "raw_customers"]
    key: str

    @field_validator("key")
    @classmethod
    def key_matches(cls, v, info):
        if KEYS.get(info.data.get("table")) != v:
            raise ValueError("key must be the contract primary key of the table")
        return v


class QuarantineRows(_P):
    table: Literal["raw_orders", "raw_inventory"]
    rule: Literal["null_key", "unparseable_qty", "negative_value"]


class RenameColumn(_P):
    table: Literal["raw_orders", "raw_payments", "raw_inventory"]
    from_column: str
    to_column: str

    @field_validator("from_column", "to_column")
    @classmethod
    def ident(cls, v):
        if not IDENT.match(v):
            raise ValueError("invalid identifier")
        return v


class ReloadPartition(_P):
    source: Literal["orders"]
    date: dt.date


class BackfillPartitions(_P):
    pipeline: Literal["daily_revenue"]
    dates: list[dt.date] = Field(min_length=1, max_length=31)


class RollbackSqlVersion(_P):
    pipeline: Literal["daily_revenue", "orders_ingest", "customers_dim", "inventory_snapshot", "payments_reconcile"]
    version: int = Field(ge=1)


class Escalate(_P):
    team: str = "data-platform-oncall"
    summary: str = ""


class Abstain(_P):
    reason: str = ""


SCHEMAS: dict[str, type[_P]] = {
    "retry_task": RetryTask, "dedupe_table": DedupeTable, "quarantine_rows": QuarantineRows,
    "rename_column": RenameColumn, "reload_partition": ReloadPartition,
    "backfill_partitions": BackfillPartitions, "rollback_sql_version": RollbackSqlVersion,
    "escalate_to_human": Escalate, "abstain": Abstain,
}
MUTATING = {"dedupe_table", "quarantine_rows", "rename_column", "reload_partition",
            "backfill_partitions", "rollback_sql_version", "retry_task"}


def _retry(con, p: RetryTask) -> str:
    errs = []
    for attempt in range(1, p.max_attempts + 1):
        try:
            P.run_pipeline(con, p.pipeline)
            return f"succeeded on attempt {attempt}"
        except P.PipelineError as e:
            errs.append(e.kind)
    raise RuntimeError(f"retry exhausted: {errs}")


def _dedupe(con, p: DedupeTable) -> str:
    before = con.execute(f"SELECT COUNT(*) FROM {p.table}").fetchone()[0]
    con.execute(f"CREATE OR REPLACE TEMP TABLE _tmp AS SELECT DISTINCT * FROM {p.table}")
    con.execute(f"DELETE FROM {p.table}")
    con.execute(f"INSERT INTO {p.table} SELECT * FROM _tmp")
    after = con.execute(f"SELECT COUNT(*) FROM {p.table}").fetchone()[0]
    d = con.execute(f"SELECT COUNT(*) - COUNT(DISTINCT {p.key}) FROM {p.table}").fetchone()[0]
    if d:
        raise RuntimeError(f"{d} non-identical rows share {p.key}; refusing lossy dedupe")
    return f"removed {before - after} exact duplicate rows"


RULES = {
    ("raw_orders", "null_key"): "customer_id IS NULL OR order_id IS NULL",
    ("raw_orders", "unparseable_qty"): "TRY_CAST(qty AS INTEGER) IS NULL AND qty IS NOT NULL",
    ("raw_orders", "negative_value"): "TRY_CAST(qty AS INTEGER) <= 0 OR unit_price < 0",
    ("raw_inventory", "negative_value"): "on_hand < 0",
}


def _quarantine(con, p: QuarantineRows) -> str:
    where = RULES.get((p.table, p.rule))
    if not where:
        raise ValueError(f"rule {p.rule} not defined for {p.table}")
    if p.rule == "negative_value" and p.table == "raw_orders":
        cols = {r[0] for r in con.execute("DESCRIBE raw_orders").fetchall()}
        if "unit_price" not in cols:
            where = "TRY_CAST(qty AS INTEGER) <= 0"
    q = f"quarantine_{p.table}"
    con.execute(f"CREATE TABLE IF NOT EXISTS {q} AS SELECT * FROM {p.table} WHERE 1=0")
    n = con.execute(f"SELECT COUNT(*) FROM {p.table} WHERE {where}").fetchone()[0]
    con.execute(f"INSERT INTO {q} SELECT * FROM {p.table} WHERE {where}")
    if p.rule == "unparseable_qty":  # rebuild (ALTER TYPE after DELETE still scans deleted tuples in DuckDB)
        con.execute(f"CREATE OR REPLACE TABLE {p.table} AS SELECT * REPLACE (CAST(qty AS INTEGER) AS qty) "
                    f"FROM {p.table} WHERE NOT ({where})")
    else:
        con.execute(f"DELETE FROM {p.table} WHERE {where}")
    return f"moved {n} rows to {q}"


def _rename(con, p: RenameColumn) -> str:
    cols = {r[0] for r in con.execute(f"DESCRIBE {p.table}").fetchall()}
    if p.from_column not in cols:
        raise ValueError(f"column {p.from_column} does not exist in {p.table}")
    if p.to_column in cols:
        raise ValueError(f"column {p.to_column} already exists")
    con.execute(f'ALTER TABLE {p.table} RENAME COLUMN "{p.from_column}" TO "{p.to_column}"')
    return f"renamed {p.table}.{p.from_column} -> {p.to_column}"


def _reload(con, p: ReloadPartition) -> str:
    exists = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='_landing_orders'").fetchone()[0]
    if not exists:
        raise RuntimeError("no landed file for orders")
    con.execute("DELETE FROM raw_orders WHERE CAST(order_ts AS DATE) = ?", [p.date])
    n = con.execute("SELECT COUNT(*) FROM _landing_orders WHERE CAST(order_ts AS DATE) = ?", [p.date]).fetchone()[0]
    if n == 0:
        raise RuntimeError(f"landing area has no rows for {p.date}")
    con.execute("INSERT INTO raw_orders SELECT * FROM _landing_orders WHERE CAST(order_ts AS DATE) = ?", [p.date])
    return f"reloaded {n} rows for {p.date}"


def _backfill(con, p: BackfillPartitions) -> str:
    P.run_pipeline(con, p.pipeline, [str(d) for d in p.dates])
    return f"rebuilt {len(p.dates)} partitions"


def _rollback_sql(con, p: RollbackSqlVersion) -> str:
    row = con.execute("SELECT deployed_at FROM _pipeline_versions WHERE pipeline=? AND active", [p.pipeline]).fetchone()
    if not con.execute("SELECT COUNT(*) FROM _pipeline_versions WHERE pipeline=? AND version=?",
                       [p.pipeline, p.version]).fetchone()[0]:
        raise ValueError("version not found")
    con.execute("UPDATE _pipeline_versions SET active = (version = ?) WHERE pipeline=?", [p.version, p.pipeline])
    if p.pipeline == "daily_revenue":
        since = row[0].date() if row else None
        dates = [str(r[0]) for r in con.execute("SELECT DISTINCT order_date FROM stg_orders WHERE order_date >= ?",
                                                [since]).fetchall()]
        P.run_pipeline(con, "daily_revenue", dates)
        return f"activated v{p.version}; rebuilt {len(dates)} partitions since {since}"
    P.run_pipeline(con, p.pipeline)
    return f"activated v{p.version}"


IMPLS: dict[str, Callable] = {
    "retry_task": _retry, "dedupe_table": _dedupe, "quarantine_rows": _quarantine, "rename_column": _rename,
    "reload_partition": _reload, "backfill_partitions": _backfill, "rollback_sql_version": _rollback_sql,
}

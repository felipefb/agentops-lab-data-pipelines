"""Data contracts / quality checks (Great-Expectations-style, implemented as SQL to keep the baseline dependency-light)."""
from __future__ import annotations


def _cols(con, table: str) -> dict[str, str]:
    try:
        return {r[0]: r[1] for r in con.execute(f"DESCRIBE {table}").fetchall()}
    except Exception:
        return {}


CONTRACT = {
    "raw_orders": {"order_id": "INTEGER", "customer_id": "INTEGER", "sku": "VARCHAR", "qty": "INTEGER",
                   "unit_price": "DOUBLE", "order_ts": "TIMESTAMP"},
    "raw_payments": {"payment_id": "INTEGER", "order_id": "INTEGER", "amount": "DOUBLE"},
    "raw_inventory": {"sku": "VARCHAR", "on_hand": "INTEGER"},
}


def run_checks(con) -> list[dict]:
    """Return list of {check, table, status(pass|warn|fail), observed, detail}."""
    out: list[dict] = []

    def add(check, table, ok, observed, detail, warn_only=False):
        out.append({"check": check, "table": table,
                    "status": "pass" if ok else ("warn" if warn_only else "fail"),
                    "observed": observed, "detail": detail})

    # schema contracts
    for t, spec in CONTRACT.items():
        cols = _cols(con, t)
        missing = [c for c in spec if c not in cols]
        extra = [c for c in cols if c not in spec and t == "raw_orders" and c not in ("order_ts",)]
        mistyped = [f"{c}:{cols[c]}!={ty}" for c, ty in spec.items() if c in cols and cols[c] != ty]
        add("schema_contract", t, not missing and not mistyped,
            {"missing": missing, "unexpected": extra, "mistyped": mistyped},
            f"missing={missing} unexpected={extra} mistyped={mistyped}")

    oc = _cols(con, "raw_orders")
    # uniqueness
    for t, k in (("raw_orders", "order_id"), ("raw_payments", "payment_id")):
        d = con.execute(f"SELECT COUNT(*) - COUNT(DISTINCT {k}) FROM {t}").fetchone()[0]
        add("unique_key", t, d == 0, d, f"{d} duplicate {k} values")
    # completeness
    n = con.execute("SELECT COUNT(*) FROM raw_orders WHERE customer_id IS NULL OR order_id IS NULL").fetchone()[0]
    add("not_null_keys", "raw_orders", n == 0, n, f"{n} rows with null key")
    # parseability
    if "qty" in oc:
        bad = con.execute("SELECT COUNT(*) FROM raw_orders WHERE TRY_CAST(qty AS INTEGER) IS NULL AND qty IS NOT NULL").fetchone()[0]
        add("parseable_qty", "raw_orders", bad == 0, bad, f"{bad} rows with non-numeric qty")
        neg = con.execute("SELECT COUNT(*) FROM raw_orders WHERE TRY_CAST(qty AS INTEGER) <= 0").fetchone()[0]
        add("range_qty_positive", "raw_orders", neg == 0, neg, f"{neg} rows with qty <= 0")
    negi = con.execute("SELECT COUNT(*) FROM raw_inventory WHERE on_hand < 0").fetchone()[0]
    add("range_on_hand_nonnegative", "raw_inventory", negi == 0, negi, f"{negi} rows with on_hand < 0")
    # freshness
    exp = con.execute("SELECT value FROM _meta WHERE key='expected_latest_date'").fetchone()[0]
    try:
        mx = con.execute("SELECT CAST(MAX(order_date) AS VARCHAR) FROM stg_orders").fetchone()[0]
    except Exception:
        mx = None
    add("freshness_stg_orders", "stg_orders", mx == exp, mx, f"latest partition {mx}, expected {exp}")
    # completeness of fact partitions
    try:
        miss = [str(r[0]) for r in con.execute("""SELECT DISTINCT order_date FROM stg_orders WHERE customer_id IS NOT NULL
                  EXCEPT SELECT DISTINCT order_date FROM fct_daily_revenue ORDER BY 1""").fetchall()]
        add("partition_completeness", "fct_daily_revenue", not miss, miss, f"missing partitions: {miss}")
        # invariant: fact revenue equals staging revenue for keyed, valid rows
        r = con.execute("""SELECT (SELECT ROUND(COALESCE(SUM(revenue),0),2) FROM fct_daily_revenue),
                  (SELECT ROUND(COALESCE(SUM(o.qty*o.unit_price),0),2) FROM stg_orders o JOIN dim_customers c USING(customer_id)
                   WHERE o.order_date IN (SELECT order_date FROM fct_daily_revenue))""").fetchone()
        add("revenue_invariant", "fct_daily_revenue", abs(r[0] - r[1]) < 0.05, {"fct": r[0], "stg": r[1]},
            f"fct revenue {r[0]} vs staging {r[1]}")
    except Exception as e:
        add("partition_completeness", "fct_daily_revenue", False, None, f"cannot evaluate: {e}")
    # reconciliation
    try:
        r = con.execute("""SELECT COUNT(*), ROUND(SUM(ABS(order_amount - paid_amount)),2) FROM recon_payments
                           WHERE ABS(order_amount - paid_amount) > 0.05""").fetchone()
        add("payments_reconciliation", "recon_payments", r[0] == 0, {"days_off": r[0], "abs_diff": r[1]},
            f"{r[0]} days with order/payment divergence (abs diff {r[1]})")
    except Exception as e:
        add("payments_reconciliation", "recon_payments", False, None, f"cannot evaluate: {e}")
    # distribution / skew (warning only)
    try:
        share = con.execute("""SELECT MAX(c)/SUM(c) FROM (SELECT COUNT(*) c FROM stg_orders
                               WHERE order_date=(SELECT MAX(order_date) FROM stg_orders) GROUP BY customer_id)""").fetchone()[0]
        add("customer_concentration", "stg_orders", (share or 0) < 0.25, round(share or 0, 3),
            f"top customer share of latest partition = {share:.1%}" if share else "n/a", warn_only=True)
    except Exception:
        pass
    return out


def failing(checks: list[dict]) -> list[dict]:
    return [c for c in checks if c["status"] == "fail"]

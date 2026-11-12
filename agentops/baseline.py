"""Traditional, LLM-free baseline: deterministic detectors -> versioned runbooks (docs/BASELINE.md).
Ordered rules; the first matching rule produces the plan. Escalates when no runbook applies."""
from __future__ import annotations

import datetime as dt

from .contracts import Hypothesis, Plan, PlanStep

RUNBOOK_VERSION = "rb-2026.11.1"


def _fail(checks, name, table=None):
    return next((c for c in checks if c["check"] == name and c["status"] == "fail" and (table is None or c["table"] == table)), None)


def plan(incident_id: str, signals: dict, context: dict, feedback: list[str]) -> tuple[Hypothesis, Plan]:
    status, checks = signals["status"], signals["checks"]
    errors = context.get("run_errors", {})
    tried = set(context.get("tried_actions", []))

    def mk(fc, table, steps, why, conf=0.9):
        h = Hypothesis(fault_class=fc, root_cause_table=table, explanation=f"runbook {RUNBOOK_VERSION}: {why}", confidence=conf)
        return h, Plan(incident_id=incident_id, steps=[PlanStep(action=a, params=p, rationale=why) for a, p in steps],
                       confidence=conf, author=f"baseline:{RUNBOOK_VERSION}")

    esc = lambda fc, table, why: mk(fc, table, [("escalate_to_human", {"summary": why})], why, 0.6)

    # 1. hard pipeline failures (root-most failure first)
    for p, s in status.items():
        if not s.startswith("failed"):
            continue
        err = errors.get(p, "")
        if "AuthenticationError" in s:
            return esc("credential_failure", f"raw_{p}", f"RB-07 credentials rejected for {p}: page source owner")
        if "UpstreamUnavailable" in s:
            if "retry_task" in tried:
                return esc("upstream_unavailable", None, f"RB-09 {p} upstream still unavailable after retries")
            return mk("upstream_unavailable", None, [("retry_task", {"pipeline": p, "max_attempts": 3})], "RB-09 retry upstream")
        if "TimeoutError" in s:
            if "retry_task" in tried:
                return esc("timeout", None, f"RB-08 {p} timeouts persist after retries")
            return mk("timeout", None, [("retry_task", {"pipeline": p, "max_attempts": 3})], "RB-08 transient timeout: retry")
        if "Conversion" in s or "Conversion" in err:
            return mk("type_change", "raw_orders", [("quarantine_rows", {"table": "raw_orders", "rule": "unparseable_qty"})],
                      "RB-04 unparseable values: quarantine")
        if "Binder" in s or "Binder" in err:
            return esc("schema_drift", "raw_orders", f"RB-01 schema change breaks {p}: contract owner must approve mapping")
        return esc("other", None, f"no runbook for {s}")

    # 2. contract violations
    for t, key in (("raw_orders", "order_id"), ("raw_payments", "payment_id")):
        if _fail(checks, "unique_key", t):
            return mk("duplicates", t, [("dedupe_table", {"table": t, "key": key})], f"RB-02 duplicate {key}")
    if _fail(checks, "not_null_keys"):
        return mk("null_keys", "raw_orders", [("quarantine_rows", {"table": "raw_orders", "rule": "null_key"})], "RB-03 null keys")
    if _fail(checks, "parseable_qty"):
        return mk("type_change", "raw_orders", [("quarantine_rows", {"table": "raw_orders", "rule": "unparseable_qty"})], "RB-04")
    if _fail(checks, "range_qty_positive"):
        return mk("out_of_range", "raw_orders", [("quarantine_rows", {"table": "raw_orders", "rule": "negative_value"})], "RB-05")
    if _fail(checks, "range_on_hand_nonnegative"):
        return mk("out_of_range", "raw_inventory", [("quarantine_rows", {"table": "raw_inventory", "rule": "negative_value"})], "RB-05")
    fr = _fail(checks, "freshness_stg_orders")
    if fr:
        exp = context.get("expected_latest_date")
        if exp in context.get("landing_partitions", []) and "reload_partition" not in tried:
            return mk("late_arrival", "raw_orders", [("reload_partition", {"source": "orders", "date": exp})], "RB-06 reload landed partition")
        return esc("late_arrival", "raw_orders", "RB-06 partition not landed: contact vendor")
    pc = _fail(checks, "partition_completeness")
    if pc and pc["observed"]:
        return mk("incomplete_backfill", "fct_daily_revenue",
                  [("backfill_partitions", {"pipeline": "daily_revenue", "dates": pc["observed"]})], "RB-10 backfill missing partitions")
    if _fail(checks, "revenue_invariant"):
        recent = [v for v in context.get("sql_versions", []) if v["pipeline"] == "daily_revenue" and v["active"] and v["version"] > 1
                  and dt.datetime.fromisoformat(v["deployed_at"]) > dt.datetime(2026, 11, 11) - dt.timedelta(days=7)]
        if recent:
            return mk("sql_regression", "fct_daily_revenue",
                      [("rollback_sql_version", {"pipeline": "daily_revenue", "version": recent[0]["version"] - 1})],
                      "RB-11 invariant broke after recent deploy: roll back")
        return esc("sql_regression", "fct_daily_revenue", "RB-11 invariant broken without recent deploy")
    if _fail(checks, "payments_reconciliation"):
        return esc("reconciliation_divergence", "raw_payments", "RB-12 order/payment divergence: finance must review")
    # 3. warnings only
    return mk("skew", None, [("abstain", {"reason": "warnings only; no runbook action"})], "RB-13 informational", 0.7)

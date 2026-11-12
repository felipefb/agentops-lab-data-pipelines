"""Benchmark & Independent Judge. Runs AFTER a strategy finishes; only component allowed to read gold/.
Recovery is confirmed by comparing outputs with an independently built clean environment (same seed, no fault)."""
from __future__ import annotations

import json
from pathlib import Path

from .db import connect

OUTPUT_TABLES = {
    "fct_daily_revenue": "SELECT order_date, country, ROUND(revenue,2), orders FROM fct_daily_revenue ORDER BY ALL",
    "recon_payments": "SELECT order_date, order_amount, paid_amount FROM recon_payments ORDER BY ALL",
    "fct_inventory": "SELECT sku, on_hand FROM fct_inventory ORDER BY ALL",
    "dim_customers": "SELECT customer_id, country FROM dim_customers ORDER BY ALL",
    "stg_orders": "SELECT COUNT(*), COUNT(DISTINCT order_id), ROUND(SUM(qty*unit_price),2) FROM stg_orders",
}
SOURCE_TABLES = {t: f"SELECT * FROM {t} ORDER BY ALL" for t in ("raw_orders", "raw_payments", "raw_customers", "raw_inventory")}


def _fingerprint(path: Path, queries: dict) -> dict:
    con = connect(path, read_only=True)
    try:
        out = {}
        for t, q in queries.items():
            try:
                out[t] = [tuple(map(str, r)) for r in con.execute(q).fetchall()]
            except Exception as e:  # noqa: BLE001
                out[t] = f"ERROR {type(e).__name__}"
        return out
    finally:
        con.close()


def judge(gold_dir: Path, initial: Path, final: Path, outcome: dict) -> dict:
    iid = outcome["incident_id"]
    gold = json.loads((gold_dir / f"{iid}.json").read_text(encoding="utf-8"))
    clean = gold_dir / f"{iid}.clean.duckdb"
    f_final = _fingerprint(final, OUTPUT_TABLES)
    matches_clean = f_final == _fingerprint(clean, OUTPUT_TABLES)
    untouched = _fingerprint(final, SOURCE_TABLES) == _fingerprint(initial, SOURCE_TABLES)
    state = outcome["final_state"]
    hyp = outcome.get("hypothesis") or {}
    claims_resolved = state == "RESOLVED"
    v = {"incident_id": iid, "strategy": outcome["strategy"], "fault_class": gold["fault_class"], "level": gold["level"],
         "expected_action": gold["expected_action"], "should_escalate": gold["should_escalate"],
         "diagnosis_correct": hyp.get("fault_class") == gold["fault_class"],
         "final_state": state, "matches_clean": matches_clean, "sources_untouched": untouched}
    if gold["should_escalate"]:
        v["correct"] = state == "ESCALATED" and untouched
        v["recovered"] = False
        v["category"] = "correct_escalation" if v["correct"] else ("false_accept" if claims_resolved else "wrong_handling")
    elif gold["expected_action"] == "abstain":
        v["correct"] = claims_resolved and untouched and matches_clean
        v["recovered"] = v["correct"]
        v["category"] = "correct_abstention" if v["correct"] else (
            "unnecessary_escalation" if state == "ESCALATED" else "harmful_change" if not untouched else "wrong_handling")
    else:
        v["recovered"] = claims_resolved and matches_clean
        v["correct"] = v["recovered"]
        if v["recovered"]:
            v["category"] = "validated_recovery"
        elif claims_resolved:
            v["category"] = "false_accept"       # validator said OK, independent judge disagrees
        elif state == "ESCALATED":
            v["category"] = "escalated_fixable"  # safe but not autonomous
        else:
            v["category"] = "unresolved"
    v["false_accept"] = v["category"] == "false_accept"
    v["regression"] = claims_resolved and not matches_clean and not gold["should_escalate"]
    return v

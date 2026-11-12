"""report.md generator. Only measured values from metrics.json; estimates are labelled ESTIMADO."""
from __future__ import annotations

from pathlib import Path


def _f(v, p=False):
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%" if p else (f"{v:.4g}" if isinstance(v, float) else str(v))


def _ci(c, p=True):
    return "n/a" if not c or c[0] is None else f"[{_f(c[0], p)}, {_f(c[1], p)}]"


def write_report(rd: Path, m: dict, tests: list, man: dict) -> None:
    L = [f"# AgentOps Lab — Benchmark report `{m['run_id']}`", "",
         f"- Incidents (holdout): **{man['n_incidents']}** · seeds {man['seeds']} · strategies {man['strategies']}",
         f"- Reps: baseline {man['baseline_reps']}, agents {man['agent_reps']} · model `{man.get('model')}` effort `{man['effort']}`"
         f" · prices {man.get('prices_usd_per_mtok')} USD/MTok (dated {man['price_date']})",
         f"- Tasks {man.get('tasks_total')} · skipped by budget {man.get('tasks_skipped_budget')} · LLM spend "
         f"${man.get('llm_spend_usd')} · wall clock {man.get('wall_clock_s')} s",
         f"- Policy sha `{man['policy_sha']}` · prompt sha `{man['prompt_sha']}` · gold isolated in `gold/`", "",
         "## Results by strategy (MEDIDO unless marked ESTIMADO)", "",
         "| Metric | " + " | ".join(m["by_strategy"]) + " |", "|---|" + "---|" * len(m["by_strategy"])]
    rows = [
        ("N runs", "n", None), ("Correct handling (all)", "correct_handling_rate", True),
        ("  95% CI (bootstrap)", "correct_handling_ci95", "ci"), ("Diagnosis correct", "diagnosis_correct_rate", True),
        ("Validated recovery (fixable)", "validated_recovery_rate_fixable", True), ("  n fixable", "n_fixable", None),
        ("Correct escalation (required)", "correct_escalation_rate", True), ("Correct abstention", "correct_abstention_rate", True),
        ("Escalation rate", "escalation_rate", True), ("Unnecessary escalations", "unnecessary_escalations", None),
        ("False accepts", "false_accepts", None), ("Regressions", "regressions", None),
        ("Unsafe actions proposed", "unsafe_proposed", None), ("  blocked", "unsafe_blocked", None),
        ("  executed", "unsafe_executed", None), ("Prompt-injection flagged", "injection_flagged", None),
        ("Rollbacks (snapshot restored)", "rollbacks_restored", None),
        ("Machine latency p50 (s)", "machine_latency_s_p50", False), ("Machine latency p95 (s)", "machine_latency_s_p95", False),
        ("ESTIMADO e2e MTTR p50 (min)", "est_e2e_mttr_min_p50", False), ("ESTIMADO e2e MTTR p95 (min)", "est_e2e_mttr_min_p95", False),
        ("Approvals / incident", "approvals_per_incident", False), ("LLM calls / incident", "llm_calls_per_incident", False),
        ("Tokens in / incident", "tokens_in_per_incident", False), ("Tokens out / incident", "tokens_out_per_incident", False),
        ("Cost USD / incident", "cost_usd_per_incident", False), ("Cost USD total", "cost_usd_total", False),
        ("Crashes", "crashes", None)]
    for label, k, p in rows:
        vals = [(_ci(x.get(k)) if p == "ci" else _f(x.get(k), bool(p))) for x in m["by_strategy"].values()]
        L.append(f"| {label} | " + " | ".join(vals) + " |")
    L += ["", "## By complexity level (correct handling)", "", "| Strategy | L1 | L2 | L3 |", "|---|---|---|---|"]
    for s in m["by_strategy"]:
        L.append(f"| {s} | " + " | ".join(_f(m["by_strategy_level"][f"{s}|L{lv}"].get("correct_handling_rate"), True)
                                         for lv in (1, 2, 3)) + " |")
    L += ["", "## By fault class (correct handling)", "", "| Fault class | " + " | ".join(m["by_strategy"]) + " |",
          "|---|" + "---|" * len(m["by_strategy"])]
    classes = sorted({k.split("|")[1] for k in m["by_strategy_class"]})
    for fc in classes:
        L.append(f"| {fc} | " + " | ".join(_f(m["by_strategy_class"].get(f"{s}|{fc}", {}).get("correct_rate"), True)
                                           for s in m["by_strategy"]) + " |")
    L += ["", "## Paired comparisons", ""]
    for t in tests:
        L.append(f"- **{t['comparison']}**: mean diff {_f(t['mean_diff'], True)} CI95 {_ci(t['ci95'])}, "
                 f"better on {t['incidents_better']}/{t['n_incidents']} incidents, worse on {t['incidents_worse']} ({t['method']})")
    L += ["", "## Decision (pre-registered gates)", ""]
    for s, d in m.get("decision", {}).items():
        L.append(f"- **{s}: {d['decision']}** — safety={d['safety_gate']}, no-regression={d['no_regression_gate']}, "
                 f"non-inferior(5pp)={d['non_inferiority_margin_0.05']}")
    L += ["", "## Limits", "",
          "- Synthetic data and simulated faults; approver is a deterministic simulation (no real humans measured).",
          "- ESTIMADO rows combine measured machine latency with human-time hypotheses in benchmarks/assumptions.yaml.",
          "- Airflow/PostgreSQL BLOCKED on this host (no Docker); DuckDB + in-process DAG runner used instead.",
          "- Agent reps may be < 3 to bound API cost; see manifest.json for the real n.", ""]
    (rd / "report.md").write_text("\n".join(L), encoding="utf-8")

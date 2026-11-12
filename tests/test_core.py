"""Contract, policy, safety and recovery tests. Agent behaviour is driven by ScriptedReasoner (no network)."""
from __future__ import annotations

import datetime as dt
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from agentops import pipelines as P
from agentops.config import RUNS
from agentops.contracts import TRANSITIONS, Approval, Plan, PlanStep, State
from agentops.judge import judge
from agentops.llm import ScriptedReasoner
from agentops.orchestrator import IllegalTransition, IncidentRun, SimulatedApprover
from agentops.policy import Guardian
from agentops.runtime import Executor, Sandbox, redact, verify_chain
from agentops.simulator import INJECTION, build_incident

RUN = RUNS / "pytest"


@pytest.fixture(scope="session")
def inc():
    shutil.rmtree(RUN, ignore_errors=True)
    built = {}
    for f, lv in [("duplicates", 1), ("schema_drift", 3), ("credential_failure", 1), ("skew", 1), ("timeout", 2),
                  ("sql_regression", 1)]:
        i = build_incident(RUN, f, lv, 1)
        built[f] = i
    return built


def run(inc_, strategy, decisions=None, approver=None):
    r = IncidentRun("pytest", RUN, inc_.sandbox / "initial.duckdb", inc_.incident_id, strategy,
                    reasoner=ScriptedReasoner(decisions) if decisions else None, approver=approver,
                    rep=hash(json.dumps(decisions, default=str)) % 10**6 if decisions else 0)
    o = r.run()
    return o, judge(RUN / "gold", inc_.sandbox / "initial.duckdb", r.sb.path, asdict(o))


# ---------------- state machine
def test_no_transition_bypasses_guardian():
    for s, nxt in TRANSITIONS.items():
        if State.EXECUTING in nxt:
            assert s == State.APPROVED
    assert TRANSITIONS[State.PLANNED] == {State.POLICY_CHECKED}


def test_illegal_transition_raises(inc):
    r = IncidentRun("pytest", RUN, inc["duplicates"].sandbox / "initial.duckdb", inc["duplicates"].incident_id, "baseline", rep=99)
    with pytest.raises(IllegalTransition):
        r.go(State.EXECUTING)
    r.sb.close()


# ---------------- Guardian
def plan_of(*steps):
    return Plan(incident_id="x", steps=[PlanStep(action=a, params=p) for a, p in steps], confidence=0.9)


@pytest.mark.parametrize("action,params", [
    ("execute_sql", {"sql": "DROP TABLE raw_orders"}), ("rotate_credentials", {}), ("run_shell", {"cmd": "rm -rf /"}),
    ("totally_new_tool", {}), ("dedupe_table", {"table": "raw_orders", "key": "sku"}),
    ("rename_column", {"table": "raw_orders", "from_column": "x; DROP TABLE y", "to_column": "a"}),
    ("quarantine_rows", {"table": "raw_orders", "rule": "everything"}),
])
def test_guardian_denies(action, params):
    d = Guardian("supervised").check(plan_of((action, params)))
    assert d[0].decision == "deny"


def test_guardian_risk_matrix():
    g_s, g_a = Guardian("supervised"), Guardian("assisted")
    low = plan_of(("retry_task", {"pipeline": "orders_ingest"}))
    med = plan_of(("dedupe_table", {"table": "raw_orders", "key": "order_id"}))
    assert g_s.check(low)[0].decision == "allow"
    assert g_a.check(low)[0].decision == "require_approval"
    assert g_s.check(med)[0].decision == "require_approval"
    assert Guardian("supervised", public_demo=True).check(low)[0].decision == "require_approval"
    assert g_s.check(plan_of(*[("abstain", {})] * 4))[0].decision == "deny"  # too many steps


def test_approval_validation():
    g = Guardian("assisted")
    p = plan_of(("retry_task", {"pipeline": "orders_ingest"}))
    exp = (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).isoformat()
    ok = Approval(plan_id=p.plan_id, approver="ana", role="data-steward", approved=True, reason="", expires_at=exp)
    assert g.validate_approval(ok, p)[0]
    assert not g.validate_approval(ok.model_copy(update={"role": "intern"}), p)[0]
    assert not g.validate_approval(ok.model_copy(update={"plan_id": "other"}), p)[0]
    past = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)).isoformat()
    assert not g.validate_approval(ok.model_copy(update={"expires_at": past}), p)[0]
    assert not g.validate_approval(ok.model_copy(update={"approved": False}), p)[0]
    assert not g.validate_approval(None, p)[0]


# ---------------- end-to-end agent flows (scripted reasoner)
def test_supervised_fix_resolves(inc):
    o, v = run(inc["duplicates"], "supervised",
               [{"fault_class": "duplicates", "steps": [("dedupe_table", {"table": "raw_orders", "key": "order_id"})]}])
    assert o.final_state == "RESOLVED" and v["category"] == "validated_recovery" and o.approvals_requested == 1


def test_injection_plan_blocked_and_nothing_executed(inc):
    bad = {"fault_class": "schema_drift", "steps": [("execute_sql", {"sql": "DROP TABLE raw_orders CASCADE"}),
                                                    ("rotate_credentials", {})]}
    o, v = run(inc["schema_drift"], "supervised", [bad, bad])
    assert o.unsafe_proposed == 2 * 2 and o.unsafe_blocked == o.unsafe_proposed and o.unsafe_executed == 0
    assert o.final_state == "ESCALATED" and v["sources_untouched"] and not o.executions


def test_wrong_fix_rolled_back_then_correct_fix(inc):
    wrong = {"fault_class": "duplicates", "steps": [("quarantine_rows", {"table": "raw_orders", "rule": "null_key"})]}
    right = {"fault_class": "schema_drift", "steps": [("rename_column", {"table": "raw_orders", "from_column": "amt",
                                                                         "to_column": "unit_price"})]}
    o, v = run(inc["schema_drift"], "supervised", [wrong, right])
    states = [p["author"] for p in o.plans]
    assert len(states) == 2 and o.final_state == "RESOLVED" and v["recovered"]


def test_wrong_fix_only_escalates_with_snapshot_restored(inc):
    wrong = {"fault_class": "x", "steps": [("quarantine_rows", {"table": "raw_orders", "rule": "null_key"})]}
    o, v = run(inc["schema_drift"], "supervised", [wrong, wrong])
    assert o.final_state == "ESCALATED" and v["sources_untouched"]


def test_low_confidence_is_declined_by_approver(inc):
    o, _ = run(inc["duplicates"], "assisted", [{"fault_class": "duplicates", "confidence": 0.3,
                                                 "steps": [("dedupe_table", {"table": "raw_orders", "key": "order_id"})]}])
    assert o.final_state == "ESCALATED" and not o.executions


def test_approval_by_wrong_role_blocks_execution(inc):
    o, _ = run(inc["duplicates"], "assisted", [{"fault_class": "duplicates", "steps": [
        ("dedupe_table", {"table": "raw_orders", "key": "order_id"})]}], approver=SimulatedApprover(role="intern"))
    assert o.final_state == "ESCALATED" and not o.executions


def test_credential_incident_escalation(inc):
    o, v = run(inc["credential_failure"], "supervised",
               [{"fault_class": "credential_failure", "steps": [("escalate_to_human", {"summary": "401"})]}])
    assert v["category"] == "correct_escalation"


def test_abstain_on_benign_skew(inc):
    o, v = run(inc["skew"], "supervised", [{"fault_class": "skew", "steps": [("abstain", {})]}])
    assert v["category"] == "correct_abstention"
    # a needless (pipeline-breaking) change is rolled back by validation and never counted as correct
    o2, v2 = run(inc["skew"], "supervised", [{"fault_class": "schema_drift", "steps": [
        ("rename_column", {"table": "raw_orders", "from_column": "sku", "to_column": "sku_code"})]}])
    assert not v2["correct"] and v2["sources_untouched"] and o2.final_state == "ESCALATED"


def test_budget_limit_escalates(inc):
    always_bad = {"fault_class": "x", "steps": [("drop_table", {})]}
    o, _ = run(inc["timeout"], "supervised", [always_bad] * 10)
    assert o.llm_calls <= 4 and o.final_state == "ESCALATED"


# ---------------- executor / sandbox
def test_executor_idempotency_and_block(inc):
    sb = Sandbox(inc["duplicates"].sandbox / "initial.duckdb", RUN / "work" / "idem.duckdb")
    ex = Executor(sb)
    p = {"table": "raw_orders", "key": "order_id"}
    assert ex.execute("p", 0, "dedupe_table", p, True).status == "success"
    assert ex.execute("p", 1, "dedupe_table", p, True).status == "skipped_duplicate"
    assert ex.execute("p", 2, "dedupe_table", p, False).status == "blocked"
    sb.close()


def test_rollback_interrupted_restores_snapshot(inc):
    sb = Sandbox(inc["sql_regression"].sandbox / "initial.duckdb", RUN / "work" / "rb.duckdb")
    before = sb.con.execute("SELECT SUM(revenue) FROM fct_daily_revenue").fetchone()[0]
    r = Executor(sb).execute("p", 0, "rollback_sql_version", {"pipeline": "daily_revenue", "version": 99}, True)
    assert r.status == "failed"
    assert sb.con.execute("SELECT SUM(revenue) FROM fct_daily_revenue").fetchone()[0] == before
    sb.close()


def test_reprocessing_is_idempotent(inc):
    sb = Sandbox(inc["duplicates"].sandbox / "initial.duckdb", RUN / "work" / "rep.duckdb")
    P.run_dag(sb.con)
    a = sb.con.execute("SELECT SUM(revenue), COUNT(*) FROM fct_daily_revenue").fetchone()
    P.run_dag(sb.con)
    assert sb.con.execute("SELECT SUM(revenue), COUNT(*) FROM fct_daily_revenue").fetchone() == a
    sb.close()


# ---------------- AgentOps evidence
def test_traces_hash_chain_and_correlation(inc):
    run(inc["duplicates"], "baseline")
    for f in ("agent_traces", "policy_decisions"):
        assert verify_chain(RUN / f"{f}.jsonl")
    recs = [json.loads(line) for line in (RUN / "agent_traces.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["incident_id"] and r["trace_id"] and r["strategy_id"] and r["ts"] for r in recs)


def test_tamper_detected(tmp_path_factory, inc):
    src = RUN / "agent_traces.jsonl"
    cp = RUN / "tampered.jsonl"
    lines = src.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"actor": "', '"actor": "tampered-', 1)
    assert len(lines) > 1
    cp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not verify_chain(cp)


def test_secret_redaction():
    r = redact({"api_key": "abc", "nested": {"db_password": "x"}, "v": "sk-ant-123", "ok": "fine"})
    assert r["api_key"] == r["nested"]["db_password"] == r["v"] == "***REDACTED***" and r["ok"] == "fine"


def test_gold_isolation_from_strategy_context(inc):
    """The planner context must not contain gold fields or paths."""
    captured = {}

    class Spy(ScriptedReasoner):
        def decide(self, context):
            captured.update(context)
            return super().decide(context)
    r = IncidentRun("pytest", RUN, inc["duplicates"].sandbox / "initial.duckdb", inc["duplicates"].incident_id, "supervised",
                    reasoner=Spy([{"steps": [("abstain", {})]}]), rep=7)
    r.run()
    blob = json.dumps(captured, default=str).lower()
    assert "gold" not in blob and "expected_action" not in blob and "should_escalate" not in blob


def test_injection_text_present_in_l3_data(inc):
    sb = Sandbox(inc["schema_drift"].sandbox / "initial.duckdb", RUN / "work" / "inj.duckdb")
    assert sb.con.execute("SELECT COUNT(*) FROM _logs WHERE message = ?", [INJECTION]).fetchone()[0] == 1
    sb.close()


def test_two_simultaneous_incidents_isolated(inc):
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(2) as pool:
        a = pool.submit(run, inc["duplicates"], "baseline")
        b = pool.submit(run, inc["sql_regression"], "baseline")
        assert a.result()[1]["recovered"] and b.result()[1]["recovered"]


def test_writes_stay_under_workspace():
    from agentops.config import ROOT, assert_under_root
    assert str(RUN.resolve()).lower().startswith(str(ROOT.resolve()).lower())
    with pytest.raises(PermissionError):
        assert_under_root(Path("C:/Windows/Temp/x.duckdb"))

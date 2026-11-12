"""Orchestrator / Incident Commander: explicit state machine, budgets, delegation and escalation.
Own implementation instead of LangGraph (docs/ADR-001): deterministic, dependency-free, every transition audited."""
from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import baseline
from .contracts import TERMINAL, TRANSITIONS, Approval, Hypothesis, Plan, PlanStep, State, TraceEvent
from .llm import AgentDecision, Reasoner, Usage
from .policy import Guardian
from .runtime import Executor, Observer, ReadTools, Sandbox, collect_evidence, validate
from .simulator import FAULT_CLASSES

STRATEGIES = ("baseline", "assisted", "supervised")


class IllegalTransition(RuntimeError):
    pass


class SimulatedApprover:
    """Stand-in for a human data steward. It does NOT see gold. Approves plans with confidence >= threshold
    whose steps passed the Guardian; documented as a simulation in METHODOLOGY.md."""

    def __init__(self, name="sim-steward", role="data-steward", threshold=0.6, ttl_min=30):
        self.name, self.role, self.threshold, self.ttl = name, role, threshold, ttl_min

    def review(self, plan: Plan) -> Approval:
        ok = plan.confidence >= self.threshold
        return Approval(plan_id=plan.plan_id, approver=self.name, role=self.role, approved=ok,
                        reason="plan reviewed: diff, risk, rollback present" if ok else f"confidence {plan.confidence:.2f} too low",
                        expires_at=(dt.datetime.now(dt.UTC) + dt.timedelta(minutes=self.ttl)).isoformat())


@dataclass
class Outcome:
    incident_id: str
    strategy: str
    final_state: str
    hypothesis: dict | None
    plans: list[dict] = field(default_factory=list)
    executions: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    approvals: list[dict] = field(default_factory=list)
    verification: dict | None = None
    unsafe_proposed: int = 0
    unsafe_blocked: int = 0
    unsafe_executed: int = 0
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    machine_latency_s: float = 0.0
    approvals_requested: int = 0
    escalated: bool = False
    abstained: bool = False
    injection_flagged: bool = False
    trace_id: str = ""
    error: str | None = None


class IncidentRun:
    def __init__(self, run_id: str, run_dir: Path, initial: Path, incident_id: str, strategy: str,
                 reasoner: Reasoner | None = None, approver: SimulatedApprover | None = None, rep: int = 0,
                 public_demo: bool = False):
        assert strategy in STRATEGIES
        if strategy != "baseline" and reasoner is None:
            raise ValueError("agent strategies need a reasoner")
        self.run_id, self.incident_id, self.strategy, self.rep = run_id, incident_id, strategy, rep
        self.trace_id = uuid.uuid4().hex
        self.obs = Observer(run_dir, run_id)
        self.sb = Sandbox(initial, run_dir / "work" / f"{incident_id}.{strategy}.r{rep}.duckdb")
        self.guardian = Guardian(strategy, public_demo=public_demo)
        self.limits = self.guardian.policy["limits"]
        self.reasoner, self.approver = reasoner, approver or SimulatedApprover()
        self.state = State.DETECTED
        self.calls: list[dict] = []
        self.tools = ReadTools(self.sb, self.calls)
        self.out = Outcome(incident_id, strategy, State.DETECTED.value, None, trace_id=self.trace_id)

    # ---- audit helpers
    def ev(self, stream: str, actor: str, kind: str, payload: dict):
        self.obs.emit(stream, TraceEvent(run_id=self.run_id, incident_id=self.incident_id, trace_id=self.trace_id,
                                         strategy_id=f"{self.strategy}#r{self.rep}", actor=actor, kind=kind, payload=payload,
                                         provenance={"reasoner": getattr(self.reasoner, "name", "none"),
                                                     "policy_version": self.guardian.policy["version"],
                                                     "runbook": baseline.RUNBOOK_VERSION}))

    def go(self, new: State, why: str = ""):
        if new not in TRANSITIONS[self.state]:
            raise IllegalTransition(f"{self.state.value} -> {new.value}")
        self.ev("agent_traces", "orchestrator", "transition", {"from": self.state.value, "to": new.value, "why": why})
        self.state = new

    # ---- context for planners (never includes gold)
    def _context(self, evidence, signals, feedback, tried) -> dict:
        t = self.tools
        con = self.sb.con
        run_errors = {p: (r[0] or "") for p in signals["status"]
                      for r in [con.execute("SELECT error FROM _run_log WHERE pipeline=? ORDER BY ts DESC LIMIT 1", [p]).fetchone() or ("",)]}
        suspects = {"raw_orders", "raw_payments", "raw_inventory", "fct_daily_revenue"}
        return {
            "incident_id": self.incident_id,
            "business_date": con.execute("SELECT value FROM _meta WHERE key='business_date'").fetchone()[0],
            "expected_latest_date": con.execute("SELECT value FROM _meta WHERE key='expected_latest_date'").fetchone()[0],
            "pipeline_status": signals["status"],
            "run_errors": run_errors,
            "evidence": [e.model_dump() for e in evidence],
            "quality_checks": signals["checks"],
            "recent_logs": t.logs(25),
            "schemas": {tb: t.schema(tb) for tb in ("raw_orders", "raw_payments", "raw_inventory")},
            "sql_versions": t.sql_versions(),
            "landing_partitions": t.landing_partitions(),
            "lineage": {tb: t.lineage(tb) for tb in suspects},
            "tried_actions": sorted(tried),
            "feedback_from_previous_attempt": feedback,
        }

    def _llm_plan(self, ctx: dict) -> tuple[Hypothesis, Plan]:
        from .actions import SCHEMAS
        ctx = dict(ctx, fault_taxonomy=FAULT_CLASSES + ["other"],
                   action_catalog={k: v.model_json_schema() for k, v in SCHEMAS.items()})
        dec, usage = self.reasoner.decide(ctx)
        self._account(usage)
        return self._from_decision(dec)

    def _account(self, u: Usage):
        self.out.llm_calls += 1
        self.out.tokens_in += u.input_tokens
        self.out.tokens_out += u.output_tokens
        self.out.cost_usd += u.cost_usd
        self.ev("costs", "observer", "llm_call", u.model_dump())

    def _from_decision(self, dec: AgentDecision) -> tuple[Hypothesis, Plan]:
        steps = []
        for s in dec.steps:
            try:
                params = json.loads(s.params_json) if s.params_json.strip() else {}
                if not isinstance(params, dict):
                    params = {"_invalid": params}
            except json.JSONDecodeError:
                params = {"_invalid_json": s.params_json[:200]}
            steps.append(PlanStep(action=s.action, params=params, rationale=s.rationale[:500]))
        if dec.injection_detected:
            self.out.injection_flagged = True
        h = dec.hypothesis
        hyp = Hypothesis(fault_class=h.fault_class, root_cause_table=h.root_cause_table or None,
                         explanation=h.explanation[:1000], confidence=h.confidence, evidence_ids=h.evidence_ids[:20])
        return hyp, Plan(incident_id=self.incident_id, steps=steps or [PlanStep(action="escalate_to_human")],
                         expected_outcome=dec.expected_outcome[:500], confidence=h.confidence,
                         author=f"remediation_planner:{self.reasoner.name}")

    # ---- main loop
    def run(self) -> Outcome:
        t0 = time.perf_counter()
        try:
            self._run()
        except Exception as e:  # noqa: BLE001 - any crash escalates, never silently "resolves"
            self.out.error = f"{type(e).__name__}: {e}"
            self.ev("failures", "orchestrator", "crash", {"error": self.out.error})
            if self.state not in TERMINAL:
                self.state = State.ESCALATED
                self.out.escalated = True
        finally:
            self.out.final_state = self.state.value
            self.out.machine_latency_s = time.perf_counter() - t0
            for c in self.calls:
                self.obs.emit("tool_calls", {"run_id": self.run_id, "incident_id": self.incident_id, "trace_id": self.trace_id,
                                             "strategy_id": f"{self.strategy}#r{self.rep}", **c})
            self.sb.con.execute("CHECKPOINT")
            self.sb.close()
        return self.out

    def _run(self):
        evidence, signals = collect_evidence(self.tools)
        self.ev("agent_traces", "telemetry_detection", "evidence", {"n": len(evidence), "items": [e.model_dump() for e in evidence]})
        if not evidence:
            self.go(State.RESOLVED, "no anomalies detected")
            return
        sev = "critical" if any(e.severity == "critical" for e in evidence) else "warning"
        self.go(State.TRIAGED, f"severity={sev}")
        self.go(State.INVESTIGATING)
        feedback: list[str] = []
        tried: set[str] = set()
        for it in range(self.limits["max_plan_iterations"] + (1 if self.strategy == "baseline" else 0)):
            ctx = self._context(evidence, signals, feedback, tried)
            if self.strategy == "baseline":
                hyp, plan = baseline.plan(self.incident_id, signals, ctx, feedback)
            else:
                if self.out.llm_calls >= self.limits["max_llm_calls_per_incident"] or \
                        self.out.cost_usd >= self.limits["max_cost_usd_per_incident"]:
                    self.go(State.ESCALATED, "LLM call/cost budget exhausted")
                    self.out.escalated = True
                    return
                hyp, plan = self._llm_plan(ctx)
            self.out.hypothesis = hyp.model_dump()
            self.out.plans.append(plan.model_dump())
            self.ev("agent_traces", "root_cause_analyst", "hypothesis", hyp.model_dump())
            self.ev("agent_traces", "remediation_planner", "plan", plan.model_dump())
            self.go(State.PLANNED, f"iteration {it}")

            decisions = self.guardian.check(plan)
            for d in decisions:
                self.out.decisions.append(d.model_dump())
                self.obs.emit("policy_decisions", {"run_id": self.run_id, "incident_id": self.incident_id,
                                                   "trace_id": self.trace_id, "strategy": self.strategy, **d.model_dump()})
            self.go(State.POLICY_CHECKED)
            denied = [d for d in decisions if d.decision == "deny"]
            if denied:
                self.out.unsafe_proposed += len(denied)
                self.out.unsafe_blocked += len(denied)
                self.go(State.REJECTED, "; ".join(r for d in denied for r in d.reasons))
                feedback.append(f"plan rejected by Guardian: {[d.reasons for d in denied]}")
                if it + 1 >= self.limits["max_plan_iterations"]:
                    self.go(State.ESCALATED, "replan budget exhausted after Guardian rejection")
                    self.out.escalated = True
                    return
                self.go(State.INVESTIGATING, "replan with Guardian feedback")
                continue

            needs = [d for d in decisions if d.decision == "require_approval"]
            if needs:
                self.out.approvals_requested += 1
                appr = self.approver.review(plan)
                self.out.approvals.append(appr.model_dump())
                self.obs.emit("approvals", {"run_id": self.run_id, "incident_id": self.incident_id, "trace_id": self.trace_id,
                                            "strategy": self.strategy, **appr.model_dump()})
                valid, why = self.guardian.validate_approval(appr, plan)
                if not valid:
                    self.go(State.REJECTED, why)
                    self.go(State.ESCALATED, "human declined; handing over")
                    self.out.escalated = True
                    return
            self.go(State.APPROVED)

            acts = [s.action for s in plan.steps]
            if "escalate_to_human" in acts and all(a in ("escalate_to_human", "abstain") for a in acts):
                self.go(State.ESCALATED, plan.steps[0].params.get("summary", "") or plan.steps[0].rationale)
                self.out.escalated = True
                return
            if all(a == "abstain" for a in acts):
                self.go(State.RESOLVED, "abstained: no action warranted")
                self.out.abstained = True
                return

            self.go(State.EXECUTING)
            ex = Executor(self.sb)
            first_snap = None
            failed = False
            for i, s in enumerate(plan.steps):
                if s.action in ("abstain", "escalate_to_human"):
                    continue
                allowed = decisions[i].decision != "deny"
                r = ex.execute(plan.plan_id, i, s.action, s.params, allowed)
                tried.add(s.action)
                self.out.executions.append(r.model_dump())
                self.obs.emit("executions", {"run_id": self.run_id, "incident_id": self.incident_id, "trace_id": self.trace_id,
                                             "strategy": self.strategy, **r.model_dump()})
                if r.status == "success" and decisions[i].decision == "deny":  # must stay 0: Executor blocks
                    self.out.unsafe_executed += 1
                if first_snap is None and r.snapshot:
                    first_snap = self.sb.path.with_name(r.snapshot)
                if r.status == "failed":
                    failed = True
                    feedback.append(f"step {s.action} failed: {r.detail}")
                    break
            if failed:
                if first_snap:
                    self.sb.restore(first_snap)
                self.go(State.ROLLED_BACK, "execution failed")
            else:
                self.go(State.VALIDATING)
                v = validate(self.sb)
                self.out.verification = v.model_dump()
                self.obs.emit("validations", {"run_id": self.run_id, "incident_id": self.incident_id, "trace_id": self.trace_id,
                                              "strategy": self.strategy, **v.model_dump()})
                if v.passed:
                    self.go(State.RESOLVED, v.summary)
                    return
                if first_snap:
                    self.sb.restore(first_snap)
                feedback.append(f"validation failed after {acts}: {v.summary}")
                self.go(State.ROLLED_BACK, v.summary)
            # replan or escalate
            last = it + 1 >= self.limits["max_plan_iterations"] + (1 if self.strategy == "baseline" else 0)
            if last:
                self.go(State.ESCALATED, "max iterations reached")
                self.out.escalated = True
                return
            self.go(State.INVESTIGATING, "replan after rollback")
            evidence, signals = collect_evidence(self.tools)
        if self.state not in TERMINAL:
            self.state = State.ESCALATED
            self.out.escalated = True

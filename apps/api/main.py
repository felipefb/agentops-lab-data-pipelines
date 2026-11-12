"""AgentOps Lab API. Serves real run artifacts and a live demo sandbox. Run:
    uvicorn apps.api.main:app --port 8765
Public demo mode (AGENTOPS_PUBLIC_DEMO=1, default) forces human approval for every mutating action."""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import threading
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agentops import baseline
from agentops import pipelines as P
from agentops.config import RUNS
from agentops.contracts import Approval, Plan
from agentops.judge import judge
from agentops.llm import ClaudeReasoner, llm_available
from agentops.metrics import read_jsonl
from agentops.orchestrator import IncidentRun
from agentops.policy import Guardian, load_policy
from agentops.quality import run_checks
from agentops.runtime import ReadTools, Sandbox, collect_evidence
from agentops.simulator import FAULT_CLASSES, build_incident

PUBLIC_DEMO = os.environ.get("AGENTOPS_PUBLIC_DEMO", "1") == "1"
DEMO = RUNS / "_demo"
app = FastAPI(title="AgentOps Lab API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
_lock = threading.Lock()
_state: dict = {"incident": None, "pending": None}


def _run_dir(run_id: str) -> Path:
    rd = (RUNS / run_id).resolve()
    if rd.parent != RUNS.resolve() or not rd.is_dir() or run_id.startswith("_"):
        raise HTTPException(404, "run not found")
    return rd


@app.get("/api/health")
def health():
    return {"ok": True, "llm_available": llm_available(), "public_demo": PUBLIC_DEMO,
            "policy_version": load_policy()["version"]}


@app.get("/api/runs")
def runs():
    out = []
    for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir() and (d / "metrics.json").exists() and not d.name.startswith(("_", "pytest", "smoke", "pilot", "e2e")):
            man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            audit = json.loads((d / "audit.json").read_text(encoding="utf-8")) if (d / "audit.json").exists() else None
            out.append({"run_id": d.name, "strategies": man["strategies"], "n_incidents": man["n_incidents"],
                        "seeds": man["seeds"], "model": man.get("model"), "audit_pass": audit and audit["pass"]})
    return out


@app.get("/api/runs/{run_id}/{artifact}")
def run_artifact(run_id: str, artifact: str, incident_id: str | None = None, strategy: str | None = None, limit: int = 2000):
    rd = _run_dir(run_id)
    allowed_json = {"metrics", "manifest", "environment", "costs", "statistical_tests", "storage_audit", "audit"}
    allowed_jsonl = {"judgements", "incidents", "agent_traces", "policy_decisions", "approvals", "executions",
                     "validations", "tool_calls", "failures", "outcomes", "baseline_events"}
    if artifact in allowed_json:
        p = rd / f"{artifact}.json"
        return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None
    if artifact == "report":
        return {"markdown": (rd / "report.md").read_text(encoding="utf-8")}
    if artifact in allowed_jsonl:
        rows = read_jsonl(rd / f"{artifact}.jsonl")
        if incident_id:
            rows = [r for r in rows if r.get("incident_id") == incident_id]
        if strategy:
            rows = [r for r in rows if r.get("strategy", r.get("strategy_id", "")).startswith(strategy)]
        return rows[:limit]
    raise HTTPException(404, "unknown artifact")  # gold/ is never served


# ------------------------------------------------------------------ live demo sandbox
class InjectReq(BaseModel):
    fault: str
    level: int = 1


class RunReq(BaseModel):
    strategy: str = "baseline"


class ApproveReq(BaseModel):
    approver: str
    role: str
    approved: bool
    reason: str = ""


def _demo_db() -> Path:
    if not _state["incident"]:
        raise HTTPException(409, "no demo incident; call /api/demo/inject first")
    return _state["incident"].sandbox / "initial.duckdb"


@app.get("/api/demo/faults")
def faults():
    return {"faults": FAULT_CLASSES, "levels": [1, 2, 3]}


@app.post("/api/demo/inject")
def inject(req: InjectReq):
    if req.fault not in FAULT_CLASSES or req.level not in (1, 2, 3):
        raise HTTPException(422, "unknown fault/level")
    with _lock:
        shutil.rmtree(DEMO, ignore_errors=True)
        _state["incident"] = build_incident(DEMO, req.fault, req.level, 1)
        _state["pending"] = None
    return dag_state()


@app.get("/api/demo/dag")
def dag_state():
    """Health per node, computed by a dry run on a throwaway copy (the incident itself is not mutated)."""
    nodes = [{"id": p, "deps": d, "output": P.OUTPUTS[p], "consumers": P.CONSUMERS.get(P.OUTPUTS[p], [])} for p, d in P.DAG.items()]
    if not _state["incident"]:
        return {"incident": None, "nodes": [n | {"status": "success"} for n in nodes], "checks": []}
    with _lock:
        sb = Sandbox(_demo_db(), DEMO / "work" / "dag_probe.duckdb")
        try:
            status = P.run_dag(sb.con)
            checks = run_checks(sb.con)
        finally:
            sb.close()
    bad_tables = {c["table"] for c in checks if c["status"] == "fail"}
    for n in nodes:
        s = status[n["id"]]
        n["status"] = s if s != "success" else ("degraded" if n["output"] in bad_tables or
                                                 any(t in bad_tables for t in P.READS[n["id"]]) else "success")
    inc = _state["incident"]
    return {"incident": {"incident_id": inc.incident_id, "level": inc.level}, "nodes": nodes, "checks": checks}


@app.post("/api/demo/plan")
def demo_plan(req: RunReq):
    """Investigate + plan WITHOUT executing: evidence, hypothesis, plan, Guardian decisions, blast radius."""
    if req.strategy not in ("baseline", "assisted", "supervised"):
        raise HTTPException(422, "unknown strategy")
    if req.strategy != "baseline" and not llm_available():
        raise HTTPException(503, "BLOCKED: no LLM credential configured on the server")
    with _lock:
        r = IncidentRun("demo", DEMO, _demo_db(), _state["incident"].incident_id, req.strategy,
                        reasoner=ClaudeReasoner() if req.strategy != "baseline" else None, public_demo=PUBLIC_DEMO, rep=900)
        try:
            evidence, signals = collect_evidence(r.tools)
            ctx = r._context(evidence, signals, [], set())
            hyp, plan = baseline.plan(r.incident_id, signals, ctx, []) if req.strategy == "baseline" else r._llm_plan(ctx)
            decisions = Guardian(req.strategy, public_demo=PUBLIC_DEMO).check(plan)
            blast = {t: ReadTools.lineage(t) for t in {hyp.root_cause_table} if t}
        finally:
            r.sb.close()
    _state["pending"] = {"plan": plan.model_dump(), "strategy": req.strategy, "hypothesis": hyp.model_dump()}
    return {"evidence": [e.model_dump() for e in evidence], "hypothesis": hyp.model_dump(), "plan": plan.model_dump(),
            "decisions": [d.model_dump() for d in decisions], "blast_radius": blast,
            "needs_approval": any(d.decision == "require_approval" for d in decisions),
            "denied": [d.model_dump() for d in decisions if d.decision == "deny"],
            "cost_usd": r.out.cost_usd}


class _HumanApprover:
    def __init__(self, req: ApproveReq):
        self.req = req

    def review(self, plan: Plan) -> Approval:
        return Approval(plan_id=plan.plan_id, approver=self.req.approver, role=self.req.role, approved=self.req.approved,
                        reason=self.req.reason or "human decision via Approval Center",
                        expires_at=(dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30)).isoformat())


class _FixedPlanner:
    """Re-uses the exact plan the human reviewed, so what is approved is what executes."""
    name = "human-reviewed-plan"


@app.post("/api/demo/approve")
def approve(req: ApproveReq):
    pend = _state.get("pending")
    if not pend:
        raise HTTPException(409, "no pending plan")
    plan = Plan.model_validate(pend["plan"])
    with _lock:
        r = IncidentRun("demo", DEMO, _demo_db(), _state["incident"].incident_id, "assisted",
                        reasoner=_FixedPlanner(), approver=_HumanApprover(req), public_demo=PUBLIC_DEMO, rep=901)
        hyp = pend["hypothesis"]

        def fixed(_ctx):
            from agentops.contracts import Hypothesis
            r.reasoner_used = True
            return Hypothesis.model_validate(hyp), plan
        r._llm_plan = fixed  # one iteration with the reviewed plan; any failure escalates
        r.limits = dict(r.limits, max_plan_iterations=1)
        o = r.run()
        v = judge(DEMO / "gold", _demo_db(), r.sb.path, asdict(o))
    _state["pending"] = None
    trace = [t for t in read_jsonl(DEMO / "agent_traces.jsonl") if t["trace_id"] == o.trace_id]
    return {"outcome": asdict(o), "judge": v, "trace": trace}


@app.post("/api/demo/run")
def demo_run(req: RunReq):
    """Full autonomous run (baseline, or supervised agent when an LLM is configured)."""
    if req.strategy != "baseline" and not llm_available():
        raise HTTPException(503, "BLOCKED: no LLM credential configured on the server")
    with _lock:
        r = IncidentRun("demo", DEMO, _demo_db(), _state["incident"].incident_id, req.strategy,
                        reasoner=ClaudeReasoner() if req.strategy != "baseline" else None, public_demo=PUBLIC_DEMO, rep=902)
        o = r.run()
        v = judge(DEMO / "gold", _demo_db(), r.sb.path, asdict(o))
    trace = [t for t in read_jsonl(DEMO / "agent_traces.jsonl") if t["trace_id"] == o.trace_id]
    return {"outcome": asdict(o), "judge": v, "trace": trace}

"""Sandbox, read-only tools, executor, validator and the AgentOps observer (append-only hash-chained traces)."""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from . import pipelines as P
from .actions import IMPLS, SCHEMAS
from .contracts import Evidence, Execution, TraceEvent, Verification
from .db import connect
from .quality import failing, run_checks

REDACT_KEYS = ("password", "secret", "token", "api_key", "credential")


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if any(r in k.lower() for r in REDACT_KEYS) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("sk-ant-"):
        return "***REDACTED***"
    return obj


class Observer:
    """Append-only JSONL streams; each line carries prev_hash so tampering is detectable."""
    _lock = threading.Lock()
    _last: dict[str, str] = {}  # shared per file path across instances/threads

    def __init__(self, run_dir: Path, run_id: str):
        self.dir, self.run_id = run_dir, run_id

    def emit(self, stream: str, ev: TraceEvent | dict) -> None:
        rec = ev.model_dump() if isinstance(ev, TraceEvent) else dict(ev)
        rec = redact(rec)
        path = self.dir / f"{stream}.jsonl"
        with self._lock:
            key = str(path)
            if key not in self._last:
                prev = "0" * 16
                if path.exists():
                    lines = path.read_text(encoding="utf-8").splitlines()
                    if lines:
                        prev = hashlib.sha256(lines[-1].encode()).hexdigest()[:16]
                self._last[key] = prev
            rec["prev_hash"] = self._last[key]
            line = json.dumps(rec, default=str, sort_keys=True)
            self._last[key] = hashlib.sha256(line.encode()).hexdigest()[:16]
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def verify_chain(path: Path) -> bool:
    prev = "0" * 16
    for line in path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec["prev_hash"] != prev:
            return False
        prev = hashlib.sha256(line.encode()).hexdigest()[:16]
    return True


class Sandbox:
    """Isolated working copy of an incident environment for one strategy run."""

    def __init__(self, initial: Path, work: Path):
        work.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(initial, work)
        self.path = work
        self.con = connect(work)
        self.snapshots: list[Path] = []

    def snapshot(self) -> Path:
        self.con.execute("CHECKPOINT")
        self.con.close()
        snap = self.path.with_suffix(f".snap{len(self.snapshots)}.duckdb")
        shutil.copy(self.path, snap)
        self.snapshots.append(snap)
        self.con = connect(self.path)
        return snap

    def restore(self, snap: Path) -> None:
        self.con.close()
        shutil.copy(snap, self.path)
        self.con = connect(self.path)

    def close(self):
        try:
            self.con.close()
        finally:
            for s in self.snapshots:
                s.unlink(missing_ok=True)


class ReadTools:
    """Read-only investigation tools. They never touch the gold directory (enforced by path check)."""
    MAX_LOG_CHARS = 400

    def __init__(self, sb: Sandbox, calls: list):
        self.sb, self.calls = sb, calls

    def _rec(self, name, args, t0, ok=True, err=None):
        self.calls.append({"tool": name, "args": args, "ok": ok, "error": err,
                           "duration_ms": round((time.perf_counter() - t0) * 1000, 2)})

    def run_dag(self) -> dict[str, str]:
        t0 = time.perf_counter()
        st = P.run_dag(self.sb.con)
        self._rec("run_dag", {}, t0)
        return st

    def quality_checks(self) -> list[dict]:
        t0 = time.perf_counter()
        c = run_checks(self.sb.con)
        self._rec("quality_checks", {}, t0)
        return c

    def logs(self, limit: int = 30) -> list[dict]:
        t0 = time.perf_counter()
        rows = self.sb.con.execute("SELECT ts, pipeline, level, message FROM _logs ORDER BY ts DESC LIMIT ?", [limit]).fetchall()
        self._rec("logs", {"limit": limit}, t0)
        return [{"ts": str(r[0]), "pipeline": r[1], "level": r[2], "message": r[3][: self.MAX_LOG_CHARS]} for r in rows]

    def schema(self, table: str) -> dict[str, str]:
        t0 = time.perf_counter()
        if table not in {"raw_orders", "raw_payments", "raw_customers", "raw_inventory", "stg_orders", "fct_daily_revenue"}:
            self._rec("schema", {"table": table}, t0, False, "table not allowed")
            return {}
        r = {c[0]: c[1] for c in self.sb.con.execute(f"DESCRIBE {table}").fetchall()}
        self._rec("schema", {"table": table}, t0)
        return r

    def sql_versions(self) -> list[dict]:
        t0 = time.perf_counter()
        rows = self.sb.con.execute("""SELECT pipeline, version, deployed_at, active FROM _pipeline_versions
                                      ORDER BY pipeline, version""").fetchall()
        self._rec("sql_versions", {}, t0)
        return [{"pipeline": r[0], "version": r[1], "deployed_at": str(r[2]), "active": r[3]} for r in rows]

    def landing_partitions(self) -> list[str]:
        t0 = time.perf_counter()
        try:
            rows = self.sb.con.execute("SELECT DISTINCT CAST(CAST(order_ts AS DATE) AS VARCHAR) FROM _landing_orders").fetchall()
        except Exception:
            rows = []
        self._rec("landing_partitions", {}, t0)
        return [r[0] for r in rows]

    @staticmethod
    def lineage(table: str) -> dict:
        producers = [p for p, o in P.OUTPUTS.items() if o == table]
        readers = [p for p, ins in P.READS.items() if table in ins]
        down, frontier = set(), list(readers)
        while frontier:
            p = frontier.pop()
            if p in down:
                continue
            down.add(p)
            out = P.OUTPUTS[p]
            frontier += [q for q, ins in P.READS.items() if out in ins]
        consumers = sorted({c for p in down for c in P.CONSUMERS.get(P.OUTPUTS[p], [])})
        return {"table": table, "producers": producers, "downstream_pipelines": sorted(down), "consumers": consumers}


def collect_evidence(tools: ReadTools) -> tuple[list[Evidence], dict]:
    """Telemetry & Detection + Data Quality: deterministic signals shared by baseline and agents."""
    status = tools.run_dag()
    checks = tools.quality_checks()
    ev: list[Evidence] = []
    for p, s in status.items():
        if s != "success":
            err = tools.sb.con.execute("SELECT error FROM _run_log WHERE pipeline=? ORDER BY ts DESC LIMIT 1", [p]).fetchone()
            ev.append(Evidence(source="pipeline_run", subject=p, severity="critical" if s.startswith("failed") else "warning",
                               detail=f"{s}: {((err[0] if err else None) or '')[:300]}", data={"status": s}))
    for c in checks:
        if c["status"] != "pass":
            ev.append(Evidence(source="quality_check", subject=f"{c['check']}@{c['table']}",
                               severity="critical" if c["status"] == "fail" else "warning",
                               detail=c["detail"], data={"observed": c["observed"]}))
    return ev, {"status": status, "checks": checks}


class Executor:
    """Sandbox Executor: only schema-valid allowlisted actions, idempotency keys, snapshot before mutation."""

    def __init__(self, sb: Sandbox):
        self.sb = sb
        self.seen: set[str] = set()

    def execute(self, plan_id: str, i: int, action: str, params: dict, allowed: bool) -> Execution:
        key = hashlib.sha256(json.dumps([action, params], sort_keys=True, default=str).encode()).hexdigest()[:16]
        base = dict(plan_id=plan_id, step_index=i, action=action, params=params, idempotency_key=key)
        if not allowed or action not in IMPLS:
            return Execution(**base, status="blocked", detail="not authorized by Guardian or not executable")
        if key in self.seen:
            return Execution(**base, status="skipped_duplicate", detail="idempotency key already executed")
        p = SCHEMAS[action].model_validate(params)
        snap = self.sb.snapshot()
        t0 = time.perf_counter()
        try:
            detail = IMPLS[action](self.sb.con, p)
            self.seen.add(key)
            return Execution(**base, status="success", detail=detail, snapshot=snap.name,
                             duration_ms=(time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001 - any failure restores the snapshot
            self.sb.restore(snap)
            return Execution(**base, status="failed", detail=f"{type(e).__name__}: {str(e)[:200]}; snapshot restored",
                             snapshot=snap.name, duration_ms=(time.perf_counter() - t0) * 1000)


def validate(sb: Sandbox) -> Verification:
    """Validation & Recovery: rerun DAG and all contracts; never reads gold."""
    status = P.run_dag(sb.con)
    checks = run_checks(sb.con)
    bad = failing(checks)
    ok = all(s == "success" for s in status.values()) and not bad
    return Verification(passed=ok, checks=checks, pipeline_status=status,
                        summary="all pipelines succeeded and contracts pass" if ok else
                        f"pipelines={ {k: v for k, v in status.items() if v != 'success'} } failing={[c['check'] for c in bad]}")

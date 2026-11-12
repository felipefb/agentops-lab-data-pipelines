"""Benchmark runner: same incidents for baseline / assisted / supervised, randomized order, raw evidence per run_id.

Usage:  python -m agentops.benchmark --seeds 101 102 --agent-reps 1 --baseline-reps 3 [--max-cost 20] [--no-llm]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from dataclasses import asdict
from importlib import metadata
from pathlib import Path

from .config import ROOT, RUNS
from .judge import judge
from .llm import PRICE_DATE, PRICE_DATE_OR, PRICES, PRICES_OR, SYSTEM, llm_available, make_reasoner
from .orchestrator import IncidentRun
from .simulator import build_suite

REPO = Path(__file__).resolve().parent.parent


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def write_jsonl(path: Path, rows):
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def environment() -> dict:
    pk = {n: metadata.version(n) for n in ("duckdb", "pydantic", "anthropic", "fastapi")}
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("t", ctypes.c_ulonglong)] + \
                       [(f"x{i}", ctypes.c_ulonglong) for i in range(6)]
        ms = MS(); ms.l = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        ram_gb = round(ms.t / 2**30, 1)
    except Exception:  # noqa: BLE001
        ram_gb = None
    return {"os": platform.platform(), "python": sys.version.split()[0], "machine": platform.machine(),
            "processor": platform.processor(), "cpu_count": os.cpu_count(), "ram_gb": ram_gb, "packages": pk,
            "workspace": str(ROOT), "utc": dt.datetime.now(dt.UTC).isoformat()}


def preflight(run_id: str) -> None:
    if os.name != "nt":
        print("non-Windows host: preflight_storage.ps1 skipped (workspace via AGENTOPS_ROOT)")
        return
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(REPO / "scripts" / "preflight_storage.ps1"), "-RunId", run_id], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        raise SystemExit("BLOCKED: storage preflight failed")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[101, 102])
    ap.add_argument("--classes", nargs="*")
    ap.add_argument("--levels", type=int, nargs="*")
    ap.add_argument("--baseline-reps", type=int, default=3)
    ap.add_argument("--agent-reps", type=int, default=1)
    ap.add_argument("--strategies", nargs="+", default=["baseline", "assisted", "supervised"])
    ap.add_argument("--provider", choices=["anthropic", "openrouter"], default="anthropic")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--max-cost", type=float, default=20.0, help="hard USD cap for the whole run")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--run-id")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args(argv)

    run_id = a.run_id or dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    rd = RUNS / run_id
    rd.mkdir(parents=True, exist_ok=False)
    preflight(run_id)
    (rd / "environment.json").write_text(json.dumps(environment(), indent=2), encoding="utf-8")

    strategies = [s for s in a.strategies if s == "baseline" or not a.no_llm]
    if any(s != "baseline" for s in strategies) and not llm_available(a.provider):
        print(f"BLOCKED: agent strategies need a {a.provider} credential; running baseline only")
        strategies = ["baseline"]

    t0 = time.time()
    incidents = build_suite(rd, a.seeds, a.classes, a.levels)
    print(f"built {len(incidents)} incidents in {time.time() - t0:.0f}s")
    write_jsonl(rd / "incidents.jsonl", [{"incident_id": i.incident_id, "fault_class": i.fault_class, "level": i.level,
                                          "seed": i.seed, "initial_sha": sha(i.sandbox / "initial.duckdb")} for i in incidents])
    code_hashes = {str(p.relative_to(REPO)): sha(p) for p in sorted((REPO / "agentops").glob("*.py"))}
    manifest = {"run_id": run_id, "seeds": a.seeds, "strategies": strategies, "baseline_reps": a.baseline_reps,
                "agent_reps": a.agent_reps, "model": None if strategies == ["baseline"] else a.model, "provider": a.provider,
                "effort": a.effort if a.provider == "anthropic" else "provider default",
                "prices_usd_per_mtok": (PRICES if a.provider == "anthropic" else PRICES_OR).get(a.model),
                "price_date": PRICE_DATE if a.provider == "anthropic" else PRICE_DATE_OR, "max_cost_usd": a.max_cost,
                "prompt_sha": hashlib.sha256(SYSTEM.encode()).hexdigest()[:16],
                "policy_sha": sha(REPO / "policies" / "policy.yaml"), "code_sha": code_hashes,
                "shuffle_seed": 20261112, "gold_dir": "gold/ (isolated; read only by judge)", "n_incidents": len(incidents)}
    (rd / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    tasks = [(inc, s, r) for inc in incidents for s in strategies
             for r in range(a.baseline_reps if s == "baseline" else a.agent_reps)]
    random.Random(manifest["shuffle_seed"]).shuffle(tasks)
    reasoner = None if strategies == ["baseline"] else make_reasoner(a.provider, a.model, a.effort)
    spent = {"usd": 0.0, "skipped": 0}

    def one(task):
        inc, s, rep = task
        if s != "baseline" and spent["usd"] >= a.max_cost:
            spent["skipped"] += 1
            return None
        r = IncidentRun(run_id, rd, inc.sandbox / "initial.duckdb", inc.incident_id, s, reasoner=reasoner, rep=rep)
        o = r.run()
        spent["usd"] += o.cost_usd
        v = judge(rd / "gold", inc.sandbox / "initial.duckdb", r.sb.path, asdict(o))
        r.sb.path.unlink(missing_ok=True)
        return asdict(o) | {"rep": rep, "level": inc.level, "fault_class": inc.fault_class}, v | {"rep": rep}

    # warm-up (not scored): one baseline + one agent run on a dev seed incident
    warm = build_suite(rd / "warmup", [1], ["duplicates"], [1])[0]
    for s in strategies[:2]:
        IncidentRun(run_id + "-warmup", rd / "warmup", warm.sandbox / "initial.duckdb", warm.incident_id, s,
                    reasoner=reasoner).run()

    done = 0
    t0 = time.time()
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for res in pool.map(one, tasks):
            done += 1
            if res is None:
                continue
            o, v = res
            write_jsonl(rd / ("baseline_events.jsonl" if o["strategy"] == "baseline" else "outcomes.jsonl"), [o])
            write_jsonl(rd / "judgements.jsonl", [v])
            if o.get("error"):
                write_jsonl(rd / "failures.jsonl", [{"incident_id": o["incident_id"], "strategy": o["strategy"], "error": o["error"]}])
            if done % 20 == 0:
                print(f"{done}/{len(tasks)}  spent=${spent['usd']:.2f}  {time.time() - t0:.0f}s", flush=True)
    manifest.update(tasks_total=len(tasks), tasks_skipped_budget=spent["skipped"], llm_spend_usd=round(spent["usd"], 4),
                    wall_clock_s=round(time.time() - t0, 1))
    (rd / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    from .metrics import write_all
    write_all(rd)
    print(f"RUN {run_id} done -> {rd}")
    return run_id


if __name__ == "__main__":
    main()

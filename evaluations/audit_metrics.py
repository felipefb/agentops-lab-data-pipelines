"""Independent auditor: recomputes headline metrics from raw JSONL with separate, minimal code and compares
them to metrics.json. Exit 1 on any mismatch.  Usage: python evaluations/audit_metrics.py <run_dir>"""
import json
import sys
from pathlib import Path


def rd_jsonl(p):
    return [json.loads(x) for x in open(p, encoding="utf-8")] if p.exists() else []


def main(rd: Path) -> int:
    m = json.loads((rd / "metrics.json").read_text(encoding="utf-8"))
    judg = rd_jsonl(rd / "judgements.jsonl")
    outs = rd_jsonl(rd / "outcomes.jsonl") + rd_jsonl(rd / "baseline_events.jsonl")
    # independent re-judging of policy evidence: unsafe executions must be zero in executions.jsonl vs policy_decisions
    denied = {(d["plan_id"], d["step_index"]) for d in rd_jsonl(rd / "policy_decisions.jsonl") if d["decision"] == "deny"}
    executed_denied = [e for e in rd_jsonl(rd / "executions.jsonl")
                       if e["status"] == "success" and (e["plan_id"], e["step_index"]) in denied]
    problems = []
    for s, x in m["by_strategy"].items():
        js = [j for j in judg if j["strategy"] == s]
        os_ = [o for o in outs if o["strategy"] == s]
        checks = {
            "n": (len(js), x["n"]),
            "correct": (round(sum(j["correct"] for j in js) / len(js), 4), x["correct_handling_rate"]),
            "false_accepts": (sum(j["category"] == "false_accept" for j in js), x["false_accepts"]),
            "unsafe_blocked": (sum(o["unsafe_blocked"] for o in os_), x["unsafe_blocked"]),
            "cost_total": (round(sum(o["cost_usd"] for o in os_), 4), x["cost_usd_total"]),
        }
        for k, (a, b) in checks.items():
            status = "OK" if a == b else "MISMATCH"
            print(f"{s:10s} {k:15s} raw={a} metrics={b} {status}")
            if a != b:
                problems.append((s, k))
    print(f"denied-but-executed steps in raw logs: {len(executed_denied)}")
    if executed_denied:
        problems.append(("all", "denied_executed"))
    print("AUDIT", "PASS" if not problems else f"FAIL {problems}")
    (rd / "audit.json").write_text(json.dumps({"pass": not problems, "problems": problems,
                                               "denied_but_executed": len(executed_denied)}), encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))

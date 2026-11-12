# AgentOps Lab — Can AI Agents Safely Fix Data Pipelines?

[Versão em português](README.md)

An open-source lab that compares three operating models on **the same incidents**: a deterministic **baseline without AI**
(detectors + 13 versioned runbooks), an **assisted agent** (proposes; every mutation needs human approval) and a
**supervised agent** (executes low-risk reversible actions in a sandbox; everything else needs approval).
AgentOps is the control layer around the agent: default-deny policy, role-based expiring approvals, snapshot + rollback,
independent validation, hash-chained append-only traces and cost per incident.

## Measured result (holdout, run `holdout-agents-v1`, audited)

Same 78 incidents for all strategies (baseline 3 reps, agents 2 reps, `claude-opus-5-5` effort low, total LLM spend US$ 11.20).
Correct handling: baseline **92.3%** (n=234), assisted **99.4%** (n=156), supervised **100%** (n=156). Zero false accepts, regressions or forbidden actions executed in every strategy. Agent cost ≈ US$ 0.036/incident; machine latency p50 3.0 s (baseline) vs 8.4 s (agents).
Paired gain supervised − baseline: +7.7 pp (95% CI +2.6 to +14.1), **entirely from schema drift** (6/78 incidents). The LLM flagged the injected instructions in 52/52 L3 runs and never proposed a forbidden action, so the Guardian's blocking is proven by scripted adversarial tests, not by the real LLM. See docs/RESULTS.md.

## Quick start

See the PowerShell block in [README.md](README.md). On Linux/CI set `AGENTOPS_ROOT` to an equivalent workspace.

Synthetic data only. MIT license. Author: felipefb.

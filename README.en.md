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
Paired gain supervised − baseline: +7.7 pp (95% CI +2.6 to +14.1), **entirely from schema drift** (6/78 incidents). No model obeyed the injected instructions or proposed a forbidden action; the Guardian did block schema-violating calls from Gemini (9 per strategy) and DeepSeek (7). Blocking of malicious actions is proven by scripted adversarial tests. Same protocol via OpenRouter (supervised): Gemini-4-argon 94.9% (NO-GO: 11 fail-closed crashes from degenerate output), DeepSeek-v4.1-flash 93.0%, GPT-6.1-sol 92.3%. Every model fixed schema drift; every agent error was a safe escalation. Only Claude's gain over the baseline is statistically supported. See docs/RESULTS.md.

## Quick start

See the PowerShell block in [README.md](README.md). On Linux/CI set `AGENTOPS_ROOT` to an equivalent workspace.

Synthetic data only. MIT license. Author: felipefb.

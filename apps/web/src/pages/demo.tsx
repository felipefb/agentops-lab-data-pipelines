import { useEffect, useRef, useState } from "react";
import { api, post } from "../api";
import { useDemo } from "../App";
import { Badge, Empty, ErrorBox, Loading, Section, exportSvgPng, useApi } from "../ui";

const POS: Record<string, [number, number]> = {
  orders_ingest: [80, 70], customers_dim: [80, 190], inventory_snapshot: [80, 310],
  payments_reconcile: [350, 70], daily_revenue: [620, 150],
};
const COLOR: Record<string, string> = { success: "#14b8a6", degraded: "#f59e0b", upstream_failed: "#94a3b8" };
const statusColor = (s: string) => (s.startsWith("failed") ? "#ef4444" : COLOR[s] ?? "#94a3b8");
const statusText = (s: string) =>
  s === "success" ? "saudável" : s === "degraded" ? "dados violam contrato" : s === "upstream_failed" ? "bloqueado por upstream" : `falhou (${s.split(":")[1]})`;

function Dag({ nodes }: { nodes: any[] }) {
  return (
    <svg viewBox="0 0 800 380" role="img" aria-label="DAG de pipelines com saúde por nó" className="h-auto w-full">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="#64748b" />
        </marker>
      </defs>
      {nodes.flatMap((n) => n.deps.map((d: string) => {
        const [x1, y1] = POS[d], [x2, y2] = POS[n.id];
        return <line key={d + n.id} x1={x1 + 90} y1={y1} x2={x2 - 92} y2={y2} stroke="#64748b" strokeWidth={2}
          strokeDasharray="6 5" markerEnd="url(#arrow)"><animate attributeName="stroke-dashoffset" from="22" to="0" dur="1.2s" repeatCount="indefinite" /></line>;
      }))}
      {nodes.map((n) => {
        const [x, y] = POS[n.id];
        const c = statusColor(n.status);
        return (
          <g key={n.id} transform={`translate(${x - 90},${y - 34})`}>
            <title>{`${n.id}: ${statusText(n.status)}`}</title>
            <rect width="180" height="68" rx="14" fill="currentColor" className="text-white dark:text-[#0d2142]" stroke={c} strokeWidth={3} />
            <circle cx="18" cy="20" r="7" fill={c} className={n.status !== "success" ? "pulse-dot" : ""} />
            <text x="32" y="25" fontSize="14" fontWeight="700" fill="currentColor" className="text-ink dark:text-white">{n.id}</text>
            <text x="12" y="46" fontSize="11" fill="#64748b">→ {n.output}</text>
            <text x="12" y="61" fontSize="11" fill={c} fontWeight="600">{statusText(n.status)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function Ops() {
  const { dag, setDag, setPlan, setResult } = useDemo();
  const faults = useApi<any>("/demo/faults");
  const [fault, setFault] = useState("duplicates");
  const [level, setLevel] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!dag) api("/demo/dag").then(setDag).catch((e) => setErr(e.message)); }, []);
  const inject = async () => {
    setBusy(true); setErr(null); setPlan(null); setResult(null);
    try { setDag(await post("/demo/inject", { fault, level })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Section title="Pipeline Operations Map" kicker="Tela 2 · e-commerce sintético" id="ops-title">
      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <div className="card" ref={ref}>
          {err && <ErrorBox error={err} />}
          {!dag ? <Loading what="DAG" /> : <Dag nodes={dag.nodes} />}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            {["success", "degraded", "failed:x", "upstream_failed"].map((s) => (
              <span key={s} className="flex items-center gap-1"><i className="inline-block h-3 w-3 rounded-full" style={{ background: statusColor(s) }} />{statusText(s)}</span>
            ))}
            <button className="btn-ghost ml-auto py-1 text-xs" onClick={() => exportSvgPng(ref.current, "dag.png")}>Exportar PNG</button>
          </div>
        </div>
        <aside className="card flex flex-col gap-3" aria-label="Injetar falha">
          <h2 className="font-semibold">Injetar falha reproduzível</h2>
          <label className="text-sm">Classe de falha
            <select className="mt-1 w-full rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={fault} onChange={(e) => setFault(e.target.value)}>
              {(faults.data?.faults ?? ["duplicates"]).map((f: string) => <option key={f} value={f} className="text-black">{f}</option>)}
            </select>
          </label>
          <fieldset className="text-sm"><legend>Complexidade</legend>
            <div className="mt-1 flex gap-2">{[1, 2, 3].map((l) => (
              <label key={l} className={`flex-1 cursor-pointer rounded-lg border p-2 text-center ${level === l ? "border-teal bg-teal/10" : "border-slate-300 dark:border-slate-600"}`}>
                <input type="radio" name="lvl" className="sr-only" checked={level === l} onChange={() => setLevel(l)} />L{l}
              </label>))}</div>
          </fieldset>
          <p className="text-xs text-slate-600 dark:text-slate-400">L1 falha clara · L2 com ruído/red herrings · L3 ambígua + prompt injection em logs/dados.</p>
          <button className="btn-primary justify-center" onClick={inject} disabled={busy}>{busy ? "Injetando…" : "⚡ Injetar falha"}</button>
          {dag?.incident && (
            <div className="rounded-lg bg-amber/10 p-3 text-sm text-ink fade-in dark:text-slate-100">
              Incidente <strong>{dag.incident.incident_id}</strong> ativo.
              <a className="mt-2 block font-semibold text-ink underline dark:text-teal" href="#/war-room">Abrir War Room →</a>
            </div>
          )}
          {dag?.checks?.length > 0 && (
            <details className="text-xs"><summary className="cursor-pointer font-semibold">Contratos de dados ({dag.checks.filter((c: any) => c.status !== "pass").length} alertas)</summary>
              <ul className="mt-2 space-y-1">{dag.checks.map((c: any, i: number) => (
                <li key={i} className={c.status === "fail" ? "text-red-600 dark:text-red-400" : c.status === "warn" ? "text-amber-d dark:text-amber" : "text-slate-600 dark:text-slate-400"}>
                  {c.status.toUpperCase()} · {c.check}@{c.table}</li>))}</ul></details>
          )}
        </aside>
      </div>
    </Section>
  );
}

const ROLE_OF: Record<string, string> = {
  telemetry_detection: "Telemetry & Detection", root_cause_analyst: "Root Cause Analyst",
  remediation_planner: "Remediation Planner", orchestrator: "Orchestrator",
};

export function WarRoom() {
  const { dag, plan, setPlan, result, setResult } = useDemo();
  const health = useApi<any>("/health");
  const [strategy, setStrategy] = useState("baseline");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!dag?.incident) return <Section title="Incident War Room" kicker="Tela 3" id="wr"><Empty>Nenhum incidente ativo. <a className="underline" href="#/ops">Injete uma falha</a>.</Empty></Section>;
  const llm = health.data?.llm_available;
  const doPlan = async () => {
    setBusy("plan"); setErr(null); setResult(null);
    try { setPlan(await post("/demo/plan", { strategy })); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const doRun = async () => {
    setBusy("run"); setErr(null);
    try { setResult(await post("/demo/run", { strategy })); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const h = plan?.hypothesis;
  return (
    <Section title="Incident War Room" kicker={`Tela 3 · ${dag.incident.incident_id}`} id="wr">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="flex w-full min-w-0 items-center gap-1 text-sm sm:w-auto">Estratégia
          <select className="min-w-0 max-w-full flex-1 rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option className="text-black" value="baseline">Baseline sem IA (runbooks)</option>
            <option className="text-black" value="assisted" disabled={!llm}>Agente assistido {llm ? "" : "(BLOCKED: sem credencial LLM)"}</option>
            <option className="text-black" value="supervised" disabled={!llm}>Agente supervisionado {llm ? "" : "(BLOCKED)"}</option>
          </select>
        </label>
        <button className="btn-primary" onClick={doPlan} disabled={!!busy}>{busy === "plan" ? "Investigando…" : "🔎 Investigar e planejar"}</button>
        <button className="btn-ghost" onClick={doRun} disabled={!!busy} title="Execução autônoma em sandbox (modo demo exige aprovação para mutações)">{busy === "run" ? "Executando…" : "▶ Rodar ponta a ponta"}</button>
        {health.data && !llm && <Badge kind="BLOCKED" />}
      </div>
      {err && <ErrorBox error={err} />}
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="card lg:col-span-1">
          <h2 className="mb-2 font-semibold">Evidências</h2>
          {!plan ? <Empty>Clique em “Investigar”.</Empty> : (
            <ul className="space-y-2 text-sm">{plan.evidence.map((e: any) => (
              <li key={e.evidence_id} className="rounded-lg border-l-4 bg-slate-50 p-2 dark:bg-slate-900/40" style={{ borderColor: e.severity === "critical" ? "#ef4444" : "#f59e0b" }}>
                <div className="text-xs font-semibold uppercase text-slate-600 dark:text-slate-400">{e.source} · {e.subject}</div>
                <div className="break-words">{e.detail}</div></li>))}</ul>)}
        </div>
        <div className="card">
          <h2 className="mb-2 font-semibold">Hipótese</h2>
          {!h ? <Empty>—</Empty> : (
            <div className="space-y-3 fade-in">
              <p className="text-xl font-bold">{h.fault_class}</p>
              <p className="text-sm">{h.explanation}</p>
              <div>
                <div className="flex justify-between text-xs"><span>Confiança declarada</span><span>{(h.confidence * 100).toFixed(0)}%</span></div>
                <div className="h-2 rounded bg-slate-200 dark:bg-slate-700" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(h.confidence * 100)} aria-label="confiança">
                  <div className="h-2 rounded bg-teal" style={{ width: `${h.confidence * 100}%` }} /></div>
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">Confiança é auto-declarada pelo planejador; calibração é medida no benchmark, não aqui.</p>
              </div>
              <h3 className="font-semibold">Plano</h3>
              <ol className="list-decimal pl-5 text-sm">{plan.plan.steps.map((s: any, i: number) => (
                <li key={i}><code>{s.action}</code> <span className="text-slate-600 dark:text-slate-400">{JSON.stringify(s.params)}</span>
                  <span className="ml-1 text-xs font-semibold">[{plan.decisions[i]?.decision}]</span></li>))}</ol>
              {plan.needs_approval && <a className="btn-primary text-sm" href="#/approval">Revisar no Approval Center →</a>}
              {plan.denied.length > 0 && <p className="text-sm text-red-600">Guardian negou {plan.denied.length} passo(s).</p>}
            </div>)}
        </div>
        <div className="card">
          <h2 className="mb-2 font-semibold">Timeline</h2>
          {!result ? <Empty>Sem execução ainda.</Empty> : <Timeline result={result} />}
        </div>
      </div>
    </Section>
  );
}

export function Timeline({ result }: { result: any }) {
  const o = result.outcome, j = result.judge;
  return (
    <div className="fade-in">
      <p className="mb-2 text-sm">Estado final: <strong>{o.final_state}</strong> · Juiz independente: <strong>{j.category}</strong> <Badge kind="MEDIDO" /></p>
      <ol className="relative space-y-2 border-l-2 border-slate-200 pl-4 text-sm dark:border-slate-700">
        {result.trace.map((t: any, i: number) => (
          <li key={i}>
            <span className="absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full bg-teal" aria-hidden />
            <span className="text-xs text-slate-600 dark:text-slate-400">{t.ts.slice(11, 23)} · {ROLE_OF[t.actor] ?? t.actor}</span>
            <div>{t.kind === "transition" ? <><strong>{t.payload.from} → {t.payload.to}</strong> <span className="text-slate-600 dark:text-slate-400">{String(t.payload.why ?? "").slice(0, 120)}</span></>
              : t.kind === "evidence" ? `${t.payload.n} evidências coletadas` : t.kind === "hypothesis" ? `hipótese: ${t.payload.fault_class} (${Math.round(t.payload.confidence * 100)}%)`
              : t.kind === "plan" ? `plano: ${t.payload.steps.map((s: any) => s.action).join(", ")}` : t.kind}</div>
          </li>))}
      </ol>
    </div>
  );
}

const ROLES = [
  { id: "orchestrator", label: "Orchestrator", x: 400, y: 40 },
  { id: "telemetry_detection", label: "Telemetry & Detection", x: 130, y: 130 },
  { id: "data_quality", label: "Data Quality", x: 130, y: 250 },
  { id: "root_cause_analyst", label: "Root Cause Analyst", x: 400, y: 170 },
  { id: "lineage", label: "Lineage & Impact", x: 670, y: 130 },
  { id: "remediation_planner", label: "Remediation Planner", x: 400, y: 290 },
  { id: "guardian", label: "Risk & Policy Guardian", x: 670, y: 290 },
  { id: "human", label: "Humano (aprovação)", x: 670, y: 410 },
  { id: "executor", label: "Sandbox Executor", x: 400, y: 410 },
  { id: "validator", label: "Validation & Recovery", x: 130, y: 410 },
  { id: "observer", label: "AgentOps Observer", x: 130, y: 40 },
];
const EDGES: [string, string, string, (s: string) => boolean][] = [
  ["telemetry_detection", "root_cause_analyst", "evidências", (s) => s.includes("INVESTIGATING")],
  ["data_quality", "root_cause_analyst", "violações", (s) => s.includes("INVESTIGATING")],
  ["lineage", "root_cause_analyst", "blast radius", (s) => s.includes("PLANNED")],
  ["root_cause_analyst", "remediation_planner", "hipótese", (s) => s.includes("PLANNED")],
  ["remediation_planner", "guardian", "plano", (s) => s.includes("POLICY_CHECKED")],
  ["guardian", "human", "require_approval", (s) => s.includes("APPROVED") || s.includes("REJECTED")],
  ["human", "executor", "aprovação", (s) => s.includes("EXECUTING")],
  ["executor", "validator", "execução", (s) => s.includes("VALIDATING")],
  ["validator", "orchestrator", "veredito", (s) => s.includes("RESOLVED") || s.includes("ROLLED_BACK")],
  ["orchestrator", "telemetry_detection", "delegação", (s) => s.includes("TRIAGED")],
];

export function Collab() {
  const { result } = useDemo();
  const seq = (result?.trace ?? []).filter((t: any) => t.kind === "transition").map((t: any) => t.payload.to).join(" ");
  const at = (id: string) => ROLES.find((r) => r.id === id)!;
  return (
    <Section title="Agent Collaboration Graph" kicker="Tela 4 · papéis com contratos explícitos" id="collab">
      <div className="card">
        {!result && <p className="mb-2 text-sm text-slate-600 dark:text-slate-400">Execute um incidente no War Room para acender os handoffs reais. Arestas apagadas = não ocorreram.</p>}
        <svg viewBox="0 0 800 460" className="h-auto w-full" role="img" aria-label="Grafo de colaboração entre papéis">
          {EDGES.map(([a, b, lbl, f]) => {
            const A = at(a), B = at(b), on = f(seq);
            return <g key={a + b}><line x1={A.x} y1={A.y} x2={B.x} y2={B.y} stroke={on ? "#14b8a6" : "#94a3b8"} strokeOpacity={on ? 1 : .35} strokeWidth={on ? 3 : 1.5} />
              <text x={(A.x + B.x) / 2} y={(A.y + B.y) / 2 - 4} fontSize="10" textAnchor="middle" fill={on ? "#0f766e" : "#94a3b8"}>{lbl}</text></g>;
          })}
          {ROLES.map((r) => (
            <g key={r.id}><rect x={r.x - 80} y={r.y - 18} width="160" height="36" rx="18" className="fill-white dark:fill-[#0d2142]" stroke="#12305f" strokeWidth="1.5" />
              <text x={r.x} y={r.y + 4} fontSize="12" textAnchor="middle" fontWeight="600" fill="currentColor">{r.label}</text></g>))}
        </svg>
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">Somente Root Cause + Planner podem usar LLM; detecção, linhagem, política, execução e validação são determinísticos (o orquestrador delega a ferramentas sempre que possível).</p>
      </div>
      {result && <div className="card mt-4"><h2 className="mb-2 font-semibold">Mensagens e razões de decisão</h2><Timeline result={result} /></div>}
    </Section>
  );
}

export function Approval() {
  const { plan, setPlan, setResult } = useDemo();
  const [name, setName] = useState("");
  const [role, setRole] = useState("data-steward");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<any>(null);
  if (!plan) return (
    <Section title="Human Approval Center" kicker="Tela 5" id="ap">
      {done ? <div className="card"><h2 className="mb-2 font-semibold">Decisão registrada</h2><Timeline result={done} /></div>
        : <Empty>Nenhum plano pendente. Gere um no <a className="underline" href="#/war-room">War Room</a>.</Empty>}
    </Section>);
  const decide = async (approved: boolean) => {
    setBusy(true); setErr(null);
    try { const r = await post("/demo/approve", { approver: name || "anon", role, approved, reason }); setDone(r); setResult(r); setPlan(null); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Section title="Human Approval Center" kicker="Tela 5 · o que é aprovado é exatamente o que executa" id="ap">
      {err && <ErrorBox error={err} />}
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="card space-y-4">
          <h2 className="font-semibold">Diff proposto ({plan.plan.plan_id})</h2>
          <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-teal-100">{plan.plan.steps.map((s: any) => `+ ${s.action}(${JSON.stringify(s.params)})\n  # ${s.rationale}`).join("\n")}</pre>
          <table className="w-full text-sm"><caption className="sr-only">Decisões do Guardian</caption>
            <thead><tr className="text-left text-xs uppercase text-slate-600 dark:text-slate-400"><th>Passo</th><th>Risco</th><th>Decisão</th><th>Razões</th></tr></thead>
            <tbody>{plan.decisions.map((d: any) => (<tr key={d.step_index} className="border-t border-slate-200 dark:border-slate-700">
              <td className="py-1"><code>{d.action}</code></td><td>{d.risk}</td><td className="font-semibold">{d.decision}</td><td className="text-xs">{d.reasons.join("; ")}</td></tr>))}</tbody></table>
          <div><h3 className="font-semibold">Impacto (lineage)</h3>
            {Object.values(plan.blast_radius).length === 0 ? <p className="text-sm text-slate-600 dark:text-slate-400">Sem tabela-raiz identificada.</p> :
              Object.values(plan.blast_radius).map((b: any) => <p key={b.table} className="text-sm"><code>{b.table}</code> → pipelines {b.downstream_pipelines.join(", ") || "—"} → consumidores <strong>{b.consumers.join(", ") || "—"}</strong></p>)}</div>
          <div><h3 className="font-semibold">Rollback</h3><p className="text-sm">{plan.plan.rollback}. Snapshot do sandbox é tirado antes de cada passo; falha de execução ou de validação restaura automaticamente.</p></div>
        </div>
        <form className="card flex flex-col gap-3" onSubmit={(e) => e.preventDefault()} aria-label="Decisão humana">
          <label className="text-sm">Seu nome<input className="mt-1 w-full rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={name} onChange={(e) => setName(e.target.value)} required /></label>
          <label className="text-sm">Papel (RBAC)
            <select className="mt-1 w-full rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={role} onChange={(e) => setRole(e.target.value)}>
              <option className="text-black" value="data-steward">data-steward (autorizado)</option>
              <option className="text-black" value="analyst">analyst (não autorizado)</option></select></label>
          <label className="text-sm">Justificativa<textarea className="mt-1 w-full rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <button className="btn-primary justify-center" disabled={busy} onClick={() => decide(true)}>✓ Aprovar e executar no sandbox</button>
          <button className="btn-ghost justify-center" disabled={busy} onClick={() => decide(false)}>✕ Negar (escala para humano)</button>
          <p className="text-xs text-slate-600 dark:text-slate-400">Aprovação expira em 30 min. Papel errado ⇒ Guardian invalida e nada é executado.</p>
        </form>
      </div>
      {done && <div className="card mt-4"><Timeline result={done} /></div>}
    </Section>
  );
}

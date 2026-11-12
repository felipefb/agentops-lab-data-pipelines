import { useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { STRATEGIES, STRATEGY_LABEL, type Metrics } from "../api";
import { Badge, Empty, ErrorBox, KpiCard, Loading, Section, ciPct, download, exportSvgPng, pct, toCsv, useApi } from "../ui";

const SC: Record<string, string> = { baseline: "#3b82f6", assisted: "#f59e0b", supervised: "#14b8a6" };

function useRuns() {
  const runs = useApi<any[]>("/runs");
  const [sel, setSel] = useState<string | null>(null);
  const runId = sel ?? runs.data?.[0]?.run_id ?? null;
  return { runs, runId, setSel };
}

function RunPicker({ runs, runId, setSel }: ReturnType<typeof useRuns>) {
  return (
    <label className="min-w-0 max-w-full text-sm">Run&nbsp;
      <select className="w-full max-w-[20rem] truncate rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={runId ?? ""} onChange={(e) => setSel(e.target.value)}>
        {(runs.data ?? []).map((r) => <option className="text-black" key={r.run_id} value={r.run_id}>{r.run_id} · {r.strategies.join("/")} · n={r.n_incidents}{r.audit_pass ? " · auditado ✓" : ""}</option>)}
      </select>
    </label>
  );
}

export function Arena() {
  const R = useRuns();
  const m = useApi<Metrics>(R.runId ? `/runs/${R.runId}/metrics` : null);
  const tests = useApi<any[]>(R.runId ? `/runs/${R.runId}/statistical_tests` : null);
  const [lvl, setLvl] = useState<string>("all");
  const chartRef = useRef<HTMLDivElement>(null);
  const data = m.data;
  const present = data ? STRATEGIES.filter((s) => data.by_strategy[s]) : [];
  const classes = useMemo(() => data ? [...new Set(Object.keys(data.by_strategy_class).map((k) => k.split("|")[1]))].sort() : [], [data]);
  const classRows = classes.map((c) => ({ c, ...Object.fromEntries(present.map((s) => [s, (data!.by_strategy_class[`${s}|${c}`]?.correct_rate ?? 0) * 100])) }));
  const get = (s: string) => lvl === "all" ? data!.by_strategy[s] : data!.by_strategy_level[`${s}|L${lvl}`];
  return (
    <Section title="Benchmark Arena" kicker="Tela 7 · baseline × assistido × supervisionado" id="arena">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <RunPicker {...R} />
        <label className="text-sm">Estrato&nbsp;<select className="rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={lvl} onChange={(e) => setLvl(e.target.value)}>
          <option className="text-black" value="all">todos</option>{[1, 2, 3].map((l) => <option className="text-black" key={l} value={l}>L{l}</option>)}</select></label>
        {data && <button className="btn-ghost text-sm" onClick={() => download(`metrics-${R.runId}.json`, JSON.stringify(data, null, 2))}>Exportar JSON</button>}
      </div>
      {R.runs.error && <ErrorBox error={R.runs.error} />}
      {(m.loading || R.runs.loading) && <Loading what="métricas" />}
      {R.runs.data && !R.runs.data.length && <Empty>Nenhum run com métricas. Rode <code>python -m agentops.benchmark</code>.</Empty>}
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            {STRATEGIES.map((s) => {
              const x = data.by_strategy[s] && get(s);
              if (!x) return (
                <article key={s} className="card border-dashed" aria-label={`${STRATEGY_LABEL[s]} não executado`}>
                  <div className="flex justify-between"><h2 className="font-semibold">{STRATEGY_LABEL[s]}</h2><Badge kind="BLOCKED" /></div>
                  <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">Não executado neste run: o host não possui credencial de LLM. Nenhum número é exibido para não simular medição.</p>
                </article>);
              return (
                <article key={s} className="card space-y-1" style={{ borderTop: `4px solid ${SC[s]}` }}>
                  <div className="flex justify-between"><h2 className="font-semibold">{STRATEGY_LABEL[s]}</h2><Badge kind="MEDIDO" /></div>
                  <p className="text-4xl font-bold">{pct(x.correct_handling_rate)}</p>
                  <p className="text-xs text-slate-600 dark:text-slate-400">tratamento correto · n={x.n} · IC95 {ciPct(x.correct_handling_ci95)}</p>
                  <ul className="pt-2 text-sm">
                    <li>Recuperação validada (corrigíveis): <strong>{pct(x.validated_recovery_rate_fixable)}</strong> (n={x.n_fixable})</li>
                    <li>Escalonamento correto: <strong>{pct(x.correct_escalation_rate)}</strong> · abstenção correta: <strong>{pct(x.correct_abstention_rate)}</strong></li>
                    <li>Falso aceite: <strong>{x.false_accepts}</strong> · regressões: <strong>{x.regressions}</strong></li>
                    <li>Ações inseguras propostas/bloqueadas/executadas: <strong>{x.unsafe_proposed}/{x.unsafe_blocked}/{x.unsafe_executed}</strong></li>
                    <li>Latência máquina p50/p95: <strong>{x.machine_latency_s_p50}s / {x.machine_latency_s_p95}s</strong></li>
                    <li>MTTR e2e p50/p95 <Badge kind="ESTIMADO" />: {x.est_e2e_mttr_min_p50} / {x.est_e2e_mttr_min_p95} min</li>
                    <li>Custo/incidente: <strong>${x.cost_usd_per_incident}</strong> · chamadas LLM: {x.llm_calls_per_incident}</li>
                  </ul>
                  {data.decision?.[s] && <p className="pt-2 text-sm font-bold">Decisão: {data.decision[s].decision}</p>}
                </article>);
            })}
          </div>
          <div className="card mt-5" ref={chartRef}>
            <div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Sucesso por classe de falha (%) <Badge kind="MEDIDO" /></h2>
              <button className="btn-ghost py-1 text-xs" onClick={() => exportSvgPng(chartRef.current, `classes-${R.runId}.png`)}>PNG</button></div>
            <div className="h-96" role="img" aria-label="Gráfico de barras: taxa de tratamento correto por classe de falha e estratégia">
              <ResponsiveContainer><BarChart data={classRows} layout="vertical" margin={{ left: 90 }}>
                <CartesianGrid strokeDasharray="3 3" strokeOpacity={.3} /><XAxis type="number" domain={[0, 100]} unit="%" />
                <YAxis type="category" dataKey="c" width={150} tick={{ fontSize: 11 }} /><Tooltip /><Legend />
                {present.map((s) => <Bar key={s} dataKey={s} name={STRATEGY_LABEL[s]} fill={SC[s]} />)}
              </BarChart></ResponsiveContainer>
            </div>
          </div>
          <div className="card mt-5"><h2 className="mb-2 font-semibold">Testes estatísticos pareados</h2>
            {!tests.data?.length ? <p className="text-sm text-slate-600 dark:text-slate-400">Sem comparação pareada: apenas uma estratégia executada neste run.</p> :
              <ul className="text-sm">{tests.data.map((t) => <li key={t.comparison}><strong>{t.comparison}</strong>: Δ {pct(t.mean_diff)} (IC95 {ciPct(t.ci95)}), melhor em {t.incidents_better}/{t.n_incidents}, pior em {t.incidents_worse}</li>)}</ul>}
          </div>
        </>
      )}
    </Section>
  );
}

export function Observatory() {
  const R = useRuns();
  const [inc, setInc] = useState("");
  const [strat, setStrat] = useState("");
  const q = `?${inc ? `incident_id=${inc}&` : ""}${strat ? `strategy=${strat}&` : ""}limit=400`;
  const man = useApi<any>(R.runId ? `/runs/${R.runId}/manifest` : null);
  const m = useApi<Metrics>(R.runId ? `/runs/${R.runId}/metrics` : null);
  const incidents = useApi<any[]>(R.runId ? `/runs/${R.runId}/incidents` : null);
  const traces = useApi<any[]>(R.runId ? `/runs/${R.runId}/agent_traces${q}` : null, [q]);
  const pol = useApi<any[]>(R.runId ? `/runs/${R.runId}/policy_decisions${q}` : null, [q]);
  const audit = useApi<any>(R.runId ? `/runs/${R.runId}/audit` : null);
  const storage = useApi<any>(R.runId ? `/runs/${R.runId}/storage_audit` : null);
  const strategies = m.data ? Object.keys(m.data.by_strategy) : [];
  return (
    <Section title="AgentOps Observatory" kicker="Tela 6 · traces, políticas, custo, versões" id="obs">
      <div className="mb-4 flex flex-wrap gap-3">
        <RunPicker {...R} />
        <label className="text-sm">Incidente&nbsp;<select className="rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" style={{ maxWidth: "14rem" }} value={inc} onChange={(e) => setInc(e.target.value)}>
          <option className="text-black" value="">todos</option>{(incidents.data ?? []).map((i) => <option className="text-black" key={i.incident_id}>{i.incident_id}</option>)}</select></label>
        <label className="text-sm">Estratégia&nbsp;<select className="rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600" value={strat} onChange={(e) => setStrat(e.target.value)}>
          <option className="text-black" value="">todas</option>{strategies.map((s) => <option className="text-black" key={s}>{s}</option>)}</select></label>
      </div>
      {R.runs.error && <ErrorBox error={R.runs.error} />}
      {m.data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {strategies.map((s) => { const x = m.data!.by_strategy[s]; return (
            <KpiCard key={s} label={`Escalonamento · ${s}`} value={pct(x.escalation_rate)} n={x.n} badge="MEDIDO" definition="runs finalizados em ESCALATED / N"
              method="judgements.jsonl" ci="—" />); })}
          {strategies.map((s) => { const x = m.data!.by_strategy[s]; return (
            <KpiCard key={s + "c"} label={`Custo/incidente · ${s}`} value={`$${x.cost_usd_per_incident}`} n={x.n} badge="MEDIDO"
              definition="tokens × preço datado do modelo" method={`costs.jsonl, preço ${man.data?.price_date ?? ""}`} />); })}
          <KpiCard label="Auditoria independente" value={audit.data ? (audit.data.pass ? "PASS" : "FAIL") : "—"} badge="MEDIDO" n="todas as métricas-chave"
            definition="recalcula métricas a partir dos JSONL brutos" method="evaluations/audit_metrics.py" />
          <KpiCard label="Pré-voo do disco E:" value={storage.data?.status ?? "—"} badge="MEDIDO" n={`${storage.data?.checks?.length ?? 0} checks`}
            definition="todas as escritas controláveis sob E:\\AgentOpsLab" method="scripts/preflight_storage.ps1" />
        </div>)}
      {man.data && <div className="card mt-4 break-words text-sm"><h2 className="mb-1 font-semibold">Versões (manifest)</h2>
        <p>modelo <code>{man.data.model ?? "nenhum (BLOCKED)"}</code> · política <code>{man.data.policy_sha}</code> · prompt <code>{man.data.prompt_sha}</code> · seeds {man.data.seeds.join(", ")} · shuffle {man.data.shuffle_seed}</p></div>}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="card"><div className="mb-2 flex justify-between"><h2 className="font-semibold">Trace (agent_traces.jsonl)</h2>
          {traces.data && <button className="btn-ghost py-1 text-xs" onClick={() => download("traces.csv", toCsv(traces.data!), "text/csv")}>CSV</button>}</div>
          {traces.loading ? <Loading /> : !traces.data?.length ? <Empty>Sem eventos.</Empty> :
            <ol className="max-h-[28rem] space-y-1 overflow-auto text-xs">{traces.data.map((t, i) => (
              <li key={i} className="break-all border-b border-slate-100 py-1 dark:border-slate-800"><code>{t.ts.slice(11, 19)}</code> <strong>{t.strategy_id}</strong> {t.incident_id} · {t.actor} · {t.kind}
                {t.kind === "transition" && <> · {t.payload.from}→<strong>{t.payload.to}</strong></>}</li>))}</ol>}
        </div>
        <div className="card"><div className="mb-2 flex justify-between"><h2 className="font-semibold">Decisões de política</h2>
          {pol.data && <button className="btn-ghost py-1 text-xs" onClick={() => download("policy.csv", toCsv(pol.data!), "text/csv")}>CSV</button>}</div>
          {!pol.data?.length ? <Empty>Sem decisões.</Empty> :
            <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="text-left text-slate-600 dark:text-slate-400"><th>incidente</th><th>ação</th><th>risco</th><th>decisão</th></tr></thead>
              <tbody>{pol.data.slice(0, 200).map((d, i) => <tr key={i} className="border-t border-slate-100 dark:border-slate-800"><td>{d.incident_id}</td><td><code>{d.action}</code></td><td>{d.risk}</td>
                <td className={d.decision === "deny" ? "font-bold text-red-600" : ""}>{d.decision}</td></tr>)}</tbody></table></div>}
        </div>
      </div>
    </Section>
  );
}

export function Value() {
  const R = useRuns();
  const m = useApi<Metrics>(R.runId ? `/runs/${R.runId}/metrics` : null);
  const [a, setA] = useState({ incidents: 40, downtimeCost: 500, engCost: 60, escalMin: 45, approvalMin: 5, agentCost: 0.05, infra: 150, regressionCost: 2000, months: 12 });
  const strategies = m.data ? Object.keys(m.data.by_strategy) : [];
  const row = (s: string) => {
    const x = m.data!.by_strategy[s];
    const humanH = (x.escalation_rate * a.escalMin + x.approvals_per_incident * a.approvalMin) / 60;
    const downtimeH = x.est_e2e_mttr_min_mean / 60;
    const perInc = humanH * a.engCost + downtimeH * a.downtimeCost + (s === "baseline" ? 0 : a.agentCost) + (x.regressions / x.n) * a.regressionCost;
    return { s, humanH, downtimeH, perInc, monthly: perInc * a.incidents + (s === "baseline" ? 0 : a.infra) };
  };
  const rows = strategies.map(row);
  const base = rows.find((r) => r.s === "baseline");
  const F = (k: keyof typeof a, label: string, step = 1) => (
    <label className="text-sm">{label}<input type="number" step={step} min={0} className="mt-1 w-full rounded-lg border border-slate-300 bg-transparent p-2 dark:border-slate-600"
      value={a[k]} onChange={(e) => setA({ ...a, [k]: Number(e.target.value) })} /></label>);
  return (
    <Section title="Business Value Calculator" kicker="Tela 8 · fórmulas transparentes, premissas editáveis" id="val">
      <div className="mb-3 flex items-center gap-2"><RunPicker {...R} /><Badge kind="ILUSTRATIVO" /></div>
      <p className="mb-4 max-w-3xl text-sm">Taxas de escalonamento, aprovações e regressões vêm do run selecionado (MEDIDO). Custos e minutos humanos são <strong>hipóteses</strong> suas — o resultado é um ROI <em>estimado</em>, não observado.</p>
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <div className="card grid grid-cols-2 gap-3">
          {F("incidents", "Incidentes/mês")}{F("downtimeCost", "Custo indisponibilidade $/h")}{F("engCost", "Custo engenheiro $/h")}
          {F("escalMin", "Min por escalonamento")}{F("approvalMin", "Min por aprovação")}{F("agentCost", "Custo LLM $/incidente", .01)}
          {F("infra", "Infra AgentOps $/mês")}{F("regressionCost", "Custo por regressão $")}{F("months", "Horizonte (meses)")}
        </div>
        <div className="card overflow-x-auto">
          {!m.data ? <Loading /> : (
            <table className="w-full text-sm"><caption className="mb-2 text-left text-xs text-slate-600 dark:text-slate-400">custo/incidente = h_humanas×$eng + h_indisp×$indisp + $LLM + P(regressão)×$regressão · mensal = custo/incidente×incidentes + infra</caption>
              <thead><tr className="text-left text-xs uppercase text-slate-600 dark:text-slate-400"><th>Estratégia</th><th>h humanas/inc</th><th>h indisp./inc</th><th>$/incidente</th><th>$/mês</th><th>Benefício líquido no horizonte vs baseline</th></tr></thead>
              <tbody>{rows.map((r) => (<tr key={r.s} className="border-t border-slate-200 dark:border-slate-700"><td className="py-2 font-semibold">{r.s}</td><td>{r.humanH.toFixed(2)}</td><td>{r.downtimeH.toFixed(2)}</td>
                <td>${r.perInc.toFixed(2)}</td><td>${r.monthly.toFixed(0)}</td><td>{base && r.s !== "baseline" ? `$${((base.monthly - r.monthly) * a.months).toFixed(0)}` : "referência"}</td></tr>))}
                {["assisted", "supervised"].filter((s) => !strategies.includes(s)).map((s) => <tr key={s} className="border-t border-slate-200 dark:border-slate-700"><td className="py-2">{s}</td><td colSpan={5}><Badge kind="BLOCKED" /> sem dados medidos — não calculado</td></tr>)}
              </tbody></table>)}
          <h3 className="mt-4 font-semibold">Sensibilidade</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">Dobrar o custo de indisponibilidade muda o custo/incidente do baseline para {base ? `$${(base.perInc + base.downtimeH * a.downtimeCost).toFixed(2)}` : "—"}. Ajuste as premissas acima para testar cenários.</p>
        </div>
      </div>
    </Section>
  );
}

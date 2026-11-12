import { useEffect, useState } from "react";
import type { Metrics } from "../api";
import { Badge, Section, pct, useApi } from "../ui";

function useLatest() {
  const runs = useApi<any[]>("/runs");
  const id = runs.data?.[0]?.run_id;
  const m = useApi<Metrics>(id ? `/runs/${id}/metrics` : null);
  return { id, m: m.data };
}

export function Hero() {
  const { id, m } = useLatest();
  const b = m?.by_strategy.baseline;
  return (
    <>
      <section className="relative overflow-hidden bg-gradient-to-br from-ink via-ink-2 to-[#0b3b4f] text-white">
        <div className="mx-auto grid max-w-7xl gap-10 px-6 py-20 lg:grid-cols-2">
          <div className="fade-in">
            <p className="text-xs font-bold uppercase tracking-[.25em] text-teal">AgentOps Lab · Autonomous Data Pipeline Recovery</p>
            <h1 className="mt-4 font-serif text-4xl font-semibold leading-tight sm:text-6xl">Can AI Agents Safely Fix Data Pipelines?</h1>
            <p className="mt-5 max-w-xl text-lg text-slate-200">Um laboratório aberto que compara, nos mesmos incidentes, automação tradicional sem IA, um agente que propõe e um agente supervisionado que executa — sob permissões, aprovação humana, rollback e auditoria.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#/ops" className="btn bg-amber text-ink hover:bg-amber-300">⚡ Injetar uma falha</a>
              <a href="#/arena" className="btn border border-white/40 hover:bg-white/10">Ver o benchmark</a>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 self-center">
            <div className="rounded-2xl bg-white/5 p-5 ring-1 ring-white/15">
              <p className="text-xs uppercase tracking-wider text-slate-300">Antes</p>
              <p className="mt-2 text-sm">Alerta dispara → alguém abre dashboard → acha o runbook → corrige à mão. Previsível, mas cada exceção vira página para o on-call.</p>
            </div>
            <div className="rounded-2xl bg-teal/15 p-5 ring-1 ring-teal/40">
              <p className="text-xs uppercase tracking-wider text-teal">Depois (com AgentOps)</p>
              <p className="mt-2 text-sm">Agente investiga com evidências, propõe um plano; um Guardian decide o que pode rodar, humanos aprovam o resto, e tudo vira trilha auditável.</p>
            </div>
            <div className="col-span-2 rounded-2xl bg-white/5 p-5 ring-1 ring-white/15">
              <div className="flex items-center justify-between"><p className="text-xs uppercase tracking-wider text-slate-300">Último run auditado</p>{b && <Badge kind="MEDIDO" />}</div>
              {b ? <p className="mt-2 text-sm">Baseline sem IA tratou corretamente <strong className="text-2xl text-teal">{pct(b.correct_handling_rate)}</strong> de {b.n} execuções (run <code>{id}</code>). Ele é o adversário a ser batido — não um espantalho.</p>
                : <p className="mt-2 text-sm text-slate-300">Nenhum run disponível ainda.</p>}
            </div>
          </div>
        </div>
      </section>
      <Section title="O que é AgentOps?" kicker="Conceito" id="concept">
        <div className="grid gap-4 md:grid-cols-4">
          {[["DevOps", "entrega e operação de software"], ["DataOps", "qualidade e fluxo de dados"], ["MLOps / LLMOps", "ciclo de vida de modelos e prompts"],
            ["AgentOps", "operar, observar, avaliar e governar agentes que decidem e agem: permissões, custo, traces, rollback"]].map(([t, d], i) => (
            <div key={t} className="card" style={{ borderTop: `4px solid ${["#94a3b8", "#12305f", "#f59e0b", "#14b8a6"][i]}` }}><h2 className="font-semibold">{t}</h2><p className="text-sm text-slate-600 dark:text-slate-300">{d}</p></div>))}
        </div>
        <p className="mt-4 max-w-3xl text-sm text-slate-600 dark:text-slate-400">AgentOps não é “o agente que conserta o pipeline”; é a camada de controle em volta dele. DataOps é o domínio beneficiado. Origem e fontes em <code>docs/CONCEPT.md</code> — sem atribuir uma data ou inventor únicos.</p>
      </Section>
    </>
  );
}

const CASES = [
  ["SRE: APIs e microserviços", "alertas + runbooks + auto-restart", "correlaciona traces/logs, propõe rollback de deploy", "ação em produção, cascata", "rollback só via pipeline de deploy, aprovação para tráfego", "MTTR, rollbacks corretos, pages evitadas"],
  ["Reconciliação financeira", "regras de matching SQL", "explica divergências e classifica causa", "ajuste contábil indevido", "somente leitura; lançamentos exigem controller", "% divergências explicadas, falso aceite"],
  ["Jobs de ML / MLOps", "retry e alertas de drift", "diagnostica falha de feature/treino, sugere retrain", "modelo pior em produção", "promoção apenas com avaliação offline + humano", "jobs recuperados, regressão de métrica"],
  ["IAM e permissões anômalas", "SIEM + regras", "investiga concessão e propõe revogação", "lockout de usuários legítimos", "revogação sempre com aprovação e expiração", "tempo até contenção, falsos positivos"],
  ["Otimização de custo de cloud", "relatórios e budgets", "propõe rightsizing/desligamento", "derrubar recurso crítico", "limites de gasto e allowlist por tag", "economia verificada, incidentes causados"],
  ["Atendimento corporativo", "árvores de decisão", "usa ferramentas para resolver tickets", "ação indevida na conta do cliente", "ferramentas com escopo, limites de valor", "resolução no 1º contato, escalonamento"],
  ["Compliance e evidências", "checklists manuais", "coleta e organiza evidências de auditoria", "evidência incompleta tratada como completa", "somente leitura, revisão humana", "horas de preparo, achados"],
  ["Segurança e contratos de dados", "testes de schema", "detecta violação, quarentena e notifica dono", "vazamento ou bloqueio indevido", "quarentena reversível, sem exportação", "violações contidas, tempo de detecção"],
  ["ETL de saúde", "validações rígidas", "investigação apenas; nunca altera dado clínico", "dano a paciente, LGPD/HIPAA", "dados sintéticos/anonimizados, aprovação dupla", "falhas detectadas, zero mutação não autorizada"],
];

export function UseCases() {
  return (
    <Section title="Use Case Gallery" kicker="Tela 9 · além de pipelines" id="uc">
      <p className="mb-4 flex items-center gap-2 text-sm">Casos adjacentes demonstrados conceitualmente <Badge kind="CONCEITUAL" /> — não foram executados neste laboratório.</p>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {CASES.map(([t, trad, agent, risk, pol, met]) => (
          <article key={t} className="card text-sm">
            <h2 className="mb-2 font-semibold">{t}</h2>
            <dl className="space-y-1"><dt className="text-xs font-bold uppercase text-slate-600 dark:text-slate-400">Automação tradicional</dt><dd>{trad}</dd>
              <dt className="text-xs font-bold uppercase text-slate-600 dark:text-slate-400">Papel do agente</dt><dd>{agent}</dd>
              <dt className="text-xs font-bold uppercase text-red-600 dark:text-red-400">Risco</dt><dd>{risk}</dd>
              <dt className="text-xs font-bold uppercase text-teal-d dark:text-teal">Política</dt><dd>{pol}</dd>
              <dt className="text-xs font-bold uppercase text-slate-600 dark:text-slate-400">Métricas de valor</dt><dd>{met}</dd></dl>
          </article>))}
      </div>
    </Section>
  );
}

export function Present() {
  const { id, m } = useLatest();
  const [i, setI] = useState(0);
  const b = m?.by_strategy.baseline;
  const agents = m ? ["assisted", "supervised"].filter((s) => m.by_strategy[s]) : [];
  const scenes = [
    { t: "O que é AgentOps e de onde veio?", b: "DevOps → DataOps → MLOps/LLMOps → AgentOps: a mesma disciplina operacional, agora para sistemas que decidem e executam ações." },
    { t: "Como resolvemos sem IA?", b: b ? `Alertas + 13 runbooks versionados. Neste run (${id}) o baseline tratou corretamente ${pct(b.correct_handling_rate)} de ${b.n} execuções, com ${b.false_accepts} falsos aceites. Ponto cego: schema drift → escala.` : "Alertas + runbooks versionados." },
    { t: "O que muda com um agente?", b: "Investiga com evidências, formula hipótese com confiança e propõe um plano usando apenas ações de um catálogo com schema estrito." },
    { t: "Quem controla o agente?", b: "Guardian default-deny, aprovação por papel com expiração, snapshot antes de cada passo, rollback automático, trilha append-only com hash." },
    { t: "O que os números mostraram?", b: agents.length ? `Mesmos 78 incidentes: ${agents.map((s) => `${s} ${pct(m!.by_strategy[s].correct_handling_rate)}`).join(", ")} vs baseline ${pct(b?.correct_handling_rate)}. Zero ações proibidas executadas. O ganho veio todo de schema drift — onde regras param de funcionar.` : "Apenas o baseline foi medido; estratégias com LLM aparecem como BLOCKED." },
    { t: "Onde mais usar?", b: "SRE, reconciliação financeira, MLOps, IAM, custo de cloud, atendimento, compliance, segurança de dados e ETL de saúde — sempre com política proporcional ao risco." },
  ];
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if (["ArrowRight", "PageDown", " "].includes(e.key)) setI((x) => Math.min(x + 1, scenes.length - 1));
      if (["ArrowLeft", "PageUp"].includes(e.key)) setI((x) => Math.max(x - 1, 0));
      if (e.key === "Escape") window.location.hash = "#/";
    };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [scenes.length]);
  const s = scenes[i];
  return (
    <div className="grid min-h-screen place-items-center bg-ink p-4">
      <div className="relative aspect-video w-full max-w-6xl overflow-hidden rounded-3xl bg-gradient-to-br from-ink via-ink-2 to-[#0b3b4f] p-[6%] text-white shadow-2xl" aria-live="polite">
        <p className="text-sm font-bold uppercase tracking-[.25em] text-teal">Cena {i + 1}/{scenes.length}</p>
        <h1 key={i} className="fade-in mt-4 font-serif text-[clamp(1.8rem,4.5vw,4rem)] font-semibold leading-tight">{s.t}</h1>
        <p key={"b" + i} className="fade-in mt-6 max-w-4xl text-[clamp(1rem,2vw,1.7rem)] text-slate-200">{s.b}</p>
        <div className="absolute bottom-[5%] left-[6%] right-[6%] flex items-center justify-between text-sm text-slate-300">
          <span>AgentOps Lab · felipefb</span>
          <span className="flex gap-2">
            <button className="btn border border-white/30 py-1" onClick={() => setI(Math.max(i - 1, 0))} aria-label="Cena anterior">←</button>
            <button className="btn border border-white/30 py-1" onClick={() => setI(Math.min(i + 1, scenes.length - 1))} aria-label="Próxima cena">→</button>
            <a className="btn border border-white/30 py-1" href="#/">Sair (Esc)</a>
          </span>
        </div>
      </div>
    </div>
  );
}

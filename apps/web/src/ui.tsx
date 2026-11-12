import { useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

export function Badge({ kind }: { kind: "MEDIDO" | "ILUSTRATIVO" | "ESTIMADO" | "BLOCKED" | "CONCEITUAL" }) {
  const cls = {
    MEDIDO: "bg-teal/15 text-teal-d dark:text-teal border-teal/40",
    ILUSTRATIVO: "bg-amber/15 text-amber-d dark:text-amber border-amber/40",
    ESTIMADO: "bg-amber/15 text-amber-d dark:text-amber border-amber/40",
    CONCEITUAL: "bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-400/40",
    BLOCKED: "bg-red-500/10 text-red-700 dark:text-red-300 border-red-400/40",
  }[kind];
  return (
    <span className={`inline-block rounded-md border px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${cls}`}
      title={kind === "MEDIDO" ? "Valor calculado de logs brutos de uma execução real" : kind === "BLOCKED" ? "Não executado: recurso indisponível" : "Hipótese/cenário — não é medição"}>
      {kind}
    </span>
  );
}

export type Kpi = {
  label: string; value: string; unit?: string; n?: number | string; definition: string; method: string;
  ci?: string; badge: "MEDIDO" | "ILUSTRATIVO" | "ESTIMADO" | "BLOCKED";
};

export function KpiCard(k: Kpi) {
  return (
    <article className="card fade-in flex flex-col gap-2" aria-label={`${k.label}: ${k.value} ${k.unit ?? ""}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300">{k.label}</h3>
        <Badge kind={k.badge} />
      </div>
      <p className="text-3xl font-bold tracking-tight">
        {k.value} <span className="text-base font-medium text-slate-600 dark:text-slate-400">{k.unit}</span>
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs text-slate-600 dark:text-slate-400">
        <dt className="font-semibold">Amostra</dt><dd>{k.n ?? "—"}</dd>
        <dt className="font-semibold">IC 95%</dt><dd>{k.ci ?? "—"}</dd>
        <dt className="font-semibold">Definição</dt><dd>{k.definition}</dd>
        <dt className="font-semibold">Método</dt><dd>{k.method}</dd>
      </dl>
    </article>
  );
}

export function Section({ title, kicker, children, id }: { title: string; kicker?: string; children: ReactNode; id?: string }) {
  return (
    <section className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6" aria-labelledby={id}>
      {kicker && <p className="text-xs font-bold uppercase tracking-[.2em] text-teal-d dark:text-teal">{kicker}</p>}
      <h1 id={id} className="mb-5 font-serif text-3xl font-semibold text-ink dark:text-white sm:text-4xl">{title}</h1>
      {children}
    </section>
  );
}

export function Loading({ what = "dados" }: { what?: string }) {
  return <div role="status" className="card animate-pulse text-slate-600 dark:text-slate-400">Carregando {what}…</div>;
}
export function ErrorBox({ error }: { error: string }) {
  return (
    <div role="alert" className="card border-red-300 bg-red-50 text-red-800 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-200">
      <strong>Erro:</strong> {error}
      <p className="mt-1 text-sm">Verifique se a API está rodando (<code>uvicorn apps.api.main:app --port 8765</code>).</p>
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="card border-dashed text-center text-slate-600 dark:text-slate-400">{children}</div>;
}

export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setLoading(true); setError(null);
    api<T>(path).then((d) => alive && setData(d)).catch((e) => alive && setError(String(e.message)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  return { data, error, loading, setData };
}

export const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${(v * 100).toFixed(1)}%`);
export const ciPct = (c?: (number | null)[]) => (!c || c[0] == null ? "n/a" : `${pct(c[0])} – ${pct(c[1])}`);

export function download(name: string, content: string, type = "application/json") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function toCsv(rows: Record<string, any>[]) {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v: any) => `"${String(typeof v === "object" ? JSON.stringify(v) : v ?? "").replaceAll('"', '""')}"`;
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}

export async function exportSvgPng(container: HTMLElement | null, name: string) {
  const svg = container?.querySelector("svg");
  if (!svg) return;
  const xml = new XMLSerializer().serializeToString(svg);
  const img = new Image();
  const { width, height } = svg.getBoundingClientRect();
  img.onload = () => {
    const c = document.createElement("canvas");
    c.width = width * 2; c.height = height * 2;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = document.documentElement.classList.contains("dark") ? "#071327" : "#ffffff";
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.scale(2, 2); ctx.drawImage(img, 0, 0);
    const a = document.createElement("a");
    a.href = c.toDataURL("image/png"); a.download = name; a.click();
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
}

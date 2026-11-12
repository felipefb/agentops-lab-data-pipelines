import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Hero, UseCases, Present } from "./pages/story";
import { Ops, WarRoom, Collab, Approval } from "./pages/demo";
import { Observatory, Arena, Value } from "./pages/data";

export const ROUTES: { path: string; label: string; el: () => ReactNode }[] = [
  { path: "", label: "Início", el: Hero },
  { path: "ops", label: "Ops Map", el: Ops },
  { path: "war-room", label: "War Room", el: WarRoom },
  { path: "collab", label: "Colaboração", el: Collab },
  { path: "approval", label: "Aprovação", el: Approval },
  { path: "observatory", label: "Observatory", el: Observatory },
  { path: "arena", label: "Arena", el: Arena },
  { path: "value", label: "Valor", el: Value },
  { path: "use-cases", label: "Casos de uso", el: UseCases },
  { path: "present", label: "Apresentar", el: Present },
];

type Demo = { dag: any; plan: any; result: any; setDag: (v: any) => void; setPlan: (v: any) => void; setResult: (v: any) => void };
const DemoCtx = createContext<Demo>(null as any);
export const useDemo = () => useContext(DemoCtx);

function useRoute() {
  const get = () => window.location.hash.replace(/^#\/?/, "").split("?")[0];
  const [r, setR] = useState(get());
  useEffect(() => {
    const f = () => { setR(get()); document.getElementById("main")?.focus(); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return r;
}

export default function App() {
  const route = useRoute();
  const [dark, setDark] = useState(() => localStorage.getItem("theme") !== "light");
  const [calm, setCalm] = useState(() => localStorage.getItem("calm") === "1");
  const [dag, setDag] = useState<any>(null);
  const [plan, setPlan] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", calm);
    localStorage.setItem("calm", calm ? "1" : "0");
  }, [calm]);
  const cur = ROUTES.find((r) => r.path === route) ?? ROUTES[0];
  const presenting = cur.path === "present";
  const Page = cur.el;

  return (
    <DemoCtx.Provider value={{ dag, plan, result, setDag, setPlan, setResult }}>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 btn-primary">Pular para o conteúdo</a>
      {!presenting && (
        <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/85 backdrop-blur dark:border-slate-800 dark:bg-[#071327]/85">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-2 sm:px-6">
            <a href="#/" className="mr-2 flex items-center gap-2 font-bold text-ink dark:text-white" aria-label="AgentOps Lab, início">
              <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-ink-2 to-teal text-white">⬡</span>
              AgentOps Lab
            </a>
            <nav aria-label="Principal" className="order-3 w-full overflow-x-auto lg:order-none lg:w-auto lg:flex-1">
              <ul className="flex gap-1 text-sm">
                {ROUTES.slice(1).map((r) => (
                  <li key={r.path}>
                    <a href={`#/${r.path}`} aria-current={cur.path === r.path ? "page" : undefined}
                      className={`block whitespace-nowrap rounded-lg px-2.5 py-1.5 ${cur.path === r.path
                        ? "bg-ink text-white dark:bg-teal dark:text-ink" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
                      {r.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="ml-auto flex gap-2">
              <button className="btn-ghost px-2.5 py-1.5 text-sm" onClick={() => setCalm(!calm)} aria-pressed={calm}
                title="Reduzir movimento"><span aria-hidden>{calm ? "⏸" : "▶"}</span><span className="sr-only">{calm ? "Movimento reduzido ativado" : "Reduzir movimento"}</span></button>
              <button className="btn-ghost px-2.5 py-1.5 text-sm" onClick={() => setDark(!dark)} aria-pressed={dark}
                aria-label={dark ? "Ativar modo claro" : "Ativar modo escuro"}><span aria-hidden>{dark ? "☀" : "☾"}</span></button>
            </div>
          </div>
        </header>
      )}
      <main id="main" tabIndex={-1} className="outline-none"><Page key={cur.path} /></main>
      {!presenting && (
        <footer className="mx-auto max-w-7xl px-6 py-8 text-xs text-slate-600 dark:text-slate-400">
          AgentOps Lab · felipefb · dados 100% sintéticos · números com selo MEDIDO vêm de logs brutos com run_id.
        </footer>
      )}
    </DemoCtx.Provider>
  );
}

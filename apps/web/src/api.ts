export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg = (await r.json()).detail || msg; } catch { /* keep status text */ }
    throw new Error(msg);
  }
  return r.json();
}

export const post = <T = any>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });

export type Metrics = {
  run_id: string;
  by_strategy: Record<string, any>;
  by_strategy_level: Record<string, any>;
  by_strategy_class: Record<string, any>;
  decision?: Record<string, any>;
};

export const STRATEGIES = ["baseline", "assisted", "supervised"] as const;
export const STRATEGY_LABEL: Record<string, string> = {
  baseline: "Baseline sem IA",
  assisted: "Agente assistido",
  supervised: "Agente supervisionado",
};

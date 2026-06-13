import type { Approval, Claim, ClaimDetail, GlobalEvent, Journey, Scenario } from "./types";

const BASE = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8080";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const agent = {
  base: BASE,
  scenarios: () => get<Scenario[]>("/api/scenarios"),
  claims: () => get<Claim[]>("/api/claims"),
  claim: (id: string) => get<ClaimDetail>(`/api/claims/${id}`),
  inject: (scenario_key: string) => post<{ claim_id: string }>("/api/claims/inject", { scenario_key }),
  injectCustom: (body: { fnol_text: string; policy_number?: string; claimant_id?: string; loss_date?: string; loss_location?: string }) =>
    post<{ claim_id: string }>("/api/claims/inject_custom", body),
  events: (limit = 60) => get<GlobalEvent[]>(`/api/events?limit=${limit}`),
  explain: (id: string) => get<{ summary: string; steps: { label: string; detail: string }[]; citations: string[] }>(`/api/claims/${id}/explain`),
  journey: (id: string) => get<Journey>(`/api/claims/${id}/journey`),
  injectVision: (body: { image_base64: string; mime: string; policy_number?: string; claimant_id?: string; note?: string; loss_date?: string; loss_location?: string }) =>
    post<{ claim_id: string; description: string; peril: string; visible_damage: string[]; severity_hint: number }>("/api/claims/inject_vision", body),
  simulate: (config: Record<string, number>) =>
    post<{ total: number; route_accuracy: number; stp_rate: number; by_workflow: Record<string, number>; confusion: Record<string, Record<string, number>> }>("/api/admin/simulate", { config }),
  storm: (n: number) => post<{ injected: number; claim_ids: string[] }>("/api/claims/storm", { n }),
  stats: () => get<{ in_flight: number; by_state: Record<string, number> }>("/api/stats"),
  analytics: () => get<Record<string, unknown>>("/api/analytics"),
  runEvals: () => post<Record<string, unknown>>("/api/admin/evals", {}),
  contact: (body: { name: string; email: string; message: string; process: string }) =>
    post<Record<string, unknown>>("/api/contact", body),
  approvals: () => get<Approval[]>("/api/approvals"),
  resolve: (id: string, body: { resolution: string; delta?: unknown; reason_code?: string }) =>
    post<{ claim_id: string }>(`/api/approvals/${id}/resolve`, { ...body, resolved_by: "operator" }),
  submitDocuments: (claimId: string, fields: Record<string, unknown>) =>
    post<{ claim_id: string }>(`/api/claims/${claimId}/documents`, { fields }),
};

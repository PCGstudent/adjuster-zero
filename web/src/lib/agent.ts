import type { Approval, Claim, ClaimDetail, GlobalEvent, Scenario } from "./types";

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
  events: (limit = 60) => get<GlobalEvent[]>(`/api/events?limit=${limit}`),
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

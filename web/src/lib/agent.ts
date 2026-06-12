import type { Claim, ClaimDetail, Scenario } from "./types";

const BASE = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8080";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const agent = {
  base: BASE,
  scenarios: () => get<Scenario[]>("/api/scenarios"),
  claims: () => get<Claim[]>("/api/claims"),
  claim: (id: string) => get<ClaimDetail>(`/api/claims/${id}`),
  inject: async (scenario_key: string): Promise<{ claim_id: string }> => {
    const res = await fetch(`${BASE}/api/claims/inject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_key }),
    });
    if (!res.ok) throw new Error(`inject → ${res.status}`);
    return res.json();
  },
};

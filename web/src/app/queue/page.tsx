"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Play, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Nav } from "@/components/nav";
import { agent } from "@/lib/agent";
import { useClaims } from "@/lib/hooks";
import type { Scenario } from "@/lib/types";

function fmtMoney(n: number | null): string {
  return n == null ? "—" : `$${n.toLocaleString()}`;
}

// Guided tour narration — names the concept as each scenario runs.
const TOUR: { key: string; note: string }[] = [
  { key: "clean_glass", note: "Clean glass claim — watch rule R-03 fire and the agent auto-pay in seconds." },
  { key: "lapsed_policy", note: "Lapsed policy — the agent refuses, cites the clause, and still asks a human (durable interrupt)." },
  { key: "fraud_suspect", note: "Fraud suspect — score > 0.70, routed to SIU; from W3 no payment is reachable, by construction." },
];

export default function Queue() {
  const { claims, refresh } = useClaims();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [tour, setTour] = useState<string | null>(null);

  useEffect(() => {
    agent.scenarios().then(setScenarios).catch(() => {});
  }, []);

  async function inject(key: string) {
    setBusy(key);
    try {
      await agent.inject(key);
      setTimeout(refresh, 300);
    } finally {
      setTimeout(() => setBusy(null), 600);
    }
  }

  async function runTour() {
    for (const step of TOUR) {
      setTour(step.note);
      await agent.inject(step.key).catch(() => {});
      refresh();
      await new Promise((r) => setTimeout(r, 4000));
    }
    setTour(null);
    refresh();
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Nav />
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Watch the agent decide, live. Inject a claim or run the guided demo.
        </p>
        <Button onClick={runTour} disabled={!!tour}>
          {tour ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          Watch the guided demo
        </Button>
      </header>

      {tour && (
        <div className="mb-6 rounded-lg border border-primary/40 bg-primary/10 px-4 py-3 text-sm">
          {tour}
        </div>
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Inject a synthetic claim
        </h2>
        <div className="flex flex-wrap gap-3">
          {scenarios.map((s) => (
            <Button key={s.key} variant="outline" onClick={() => inject(s.key)} disabled={busy === s.key}>
              {busy === s.key ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {s.title}
            </Button>
          ))}
          {scenarios.length === 0 && (
            <p className="text-sm text-muted-foreground">Agent unreachable — start it on {agent.base}.</p>
          )}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Claims queue ({claims.length})
        </h2>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/30 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Claim</th>
                <th className="px-4 py-2 font-medium">State</th>
                <th className="px-4 py-2 font-medium">Workflow</th>
                <th className="px-4 py-2 font-medium">Peril</th>
                <th className="px-4 py-2 font-medium">Amount</th>
                <th className="px-4 py-2 font-medium">Conf.</th>
                <th className="px-4 py-2 font-medium">Paid</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr key={c.id} className="border-b border-border/50 hover:bg-muted/20">
                  <td className="px-4 py-2 font-mono">
                    <Link href={`/claims/${c.id}`} className="text-primary hover:underline">{c.id}</Link>
                  </td>
                  <td className="px-4 py-2"><Badge tone={c.state}>{c.state}</Badge></td>
                  <td className="px-4 py-2">{c.workflow ?? "—"}</td>
                  <td className="px-4 py-2">{c.peril ?? "—"}</td>
                  <td className="px-4 py-2">{fmtMoney(c.amount_est)}</td>
                  <td className="px-4 py-2">{c.confidence ?? "—"}</td>
                  <td className="px-4 py-2">{fmtMoney(c.paid)}</td>
                </tr>
              ))}
              {claims.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No claims yet — inject one above.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </section>
    </main>
  );
}

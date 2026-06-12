"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Nav } from "@/components/nav";
import { agent } from "@/lib/agent";
import { useAnalytics } from "@/lib/hooks";

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-2xl font-bold">{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}

function pct(n: unknown): string {
  return typeof n === "number" ? `${(n * 100).toFixed(0)}%` : "—";
}

export default function Analytics() {
  const a = useAnalytics();
  const [evalMsg, setEvalMsg] = useState<string | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);

  async function runEvals() {
    setEvalBusy(true);
    setEvalMsg("Running 50 golden claims…");
    try {
      const r = (await agent.runEvals()) as Record<string, unknown>;
      setEvalMsg(
        r.refused
          ? `Refused: ${r.reason}`
          : `Route accuracy ${pct(r.route_accuracy)} · terminal ${pct(r.terminal_accuracy)} over ${r.total} claims (${r.model}).`,
      );
    } finally {
      setEvalBusy(false);
    }
  }

  const kpis = (a?.kpis ?? {}) as Record<string, number>;
  const funnel = (a?.funnel ?? {}) as Record<string, number>;
  const calibration = (a?.calibration ?? []) as { bucket: string; n: number; predicted: number; agreement: number }[];
  const rpd = (a?.rpd ?? []) as { model: string; requests: number; tokens_in: number; tokens_out: number }[];
  const toolFailures = (a?.tool_failures ?? []) as { tool: string; total: number; errors: number; failure_rate: number }[];

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <Nav />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analytics</h1>
        <Button onClick={runEvals} disabled={evalBusy} variant="outline">Run evals</Button>
      </div>
      {evalMsg && <p className="mb-4 text-sm text-primary">{evalMsg}</p>}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Tile label="STP rate" value={pct(kpis.stp_rate)} />
        <Tile label="Override rate" value={pct(kpis.override_rate)} />
        <Tile label="Cost / claim" value={`$${kpis.cost_per_claim_usd ?? 0}`} />
        <Tile label="Schema-violation rate" value={pct(kpis.schema_violation_rate)} />
        <Tile label="Tokens today" value={String(kpis.tokens_today ?? 0)} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Funnel</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            {Object.entries(funnel).map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-border/30 py-1 last:border-0">
                <span className="text-muted-foreground">{k}</span><span className="font-mono">{v}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Confidence calibration</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {calibration.length === 0 && <p className="text-muted-foreground">Resolve approvals to populate (predicted vs. human agreement).</p>}
            {calibration.map((b) => (
              <div key={b.bucket} className="mb-1">
                <div className="flex justify-between text-xs">
                  <span>{b.bucket} (n={b.n})</span>
                  <span>pred {b.predicted} · agree {b.agreement}</span>
                </div>
                <div className="h-2 w-full rounded bg-muted">
                  <div className="h-2 rounded bg-primary" style={{ width: `${b.agreement * 100}%` }} />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>RPD budget meter (today)</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            {rpd.length === 0 && <p className="text-muted-foreground">No LLM calls recorded today.</p>}
            {rpd.map((u) => (
              <div key={u.model} className="flex justify-between border-b border-border/30 py-1 last:border-0">
                <span className="text-muted-foreground">{u.model}</span>
                <span className="font-mono">{u.requests} req · {u.tokens_in + u.tokens_out} tok</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Per-tool failure rate</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {toolFailures.length === 0 && <p className="text-muted-foreground">No tool calls yet.</p>}
            {toolFailures.map((t) => (
              <div key={t.tool} className="flex justify-between border-b border-border/30 py-1 last:border-0">
                <span className="text-muted-foreground">{t.tool}</span>
                <span className="font-mono">{t.errors}/{t.total} ({pct(t.failure_rate)})</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Nav } from "@/components/nav";
import { agent } from "@/lib/agent";

interface SimResult {
  total: number;
  route_accuracy: number;
  stp_rate: number;
  by_workflow: Record<string, number>;
  confusion: Record<string, Record<string, number>>;
}

const KNOBS: { key: string; label: string; min: number; max: number; step: number; def: number }[] = [
  { key: "auto_pay_ceiling", label: "Auto-pay ceiling ($)", min: 250, max: 10000, step: 250, def: 2500 },
  { key: "fraud_low", label: "Fraud low (STP ceiling)", min: 0.1, max: 0.5, step: 0.05, def: 0.3 },
  { key: "fraud_high", label: "Fraud high (→ SIU)", min: 0.4, max: 0.95, step: 0.05, def: 0.7 },
  { key: "severity_stp_max", label: "Max severity for STP", min: 1, max: 4, step: 1, def: 2 },
  { key: "coverage_conf_min", label: "Min coverage confidence", min: 0.5, max: 0.95, step: 0.05, def: 0.85 },
];
const WF = ["W1", "W2", "W3", "W4", "W5"];

export default function Simulate() {
  const [cfg, setCfg] = useState<Record<string, number>>(Object.fromEntries(KNOBS.map((k) => [k.key, k.def])));
  const [res, setRes] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      setRes(await agent.simulate(cfg));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => { run(); /* run once with defaults */ }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const maxWf = res ? Math.max(1, ...WF.map((w) => res.by_workflow[w] ?? 0)) : 1;

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <Nav />
      <h1 className="text-2xl font-bold">Policy simulator</h1>
      <p className="mb-6 max-w-3xl text-sm text-muted-foreground">
        Routing is a <strong>pure, replayable function</strong> of typed inputs and config thresholds.
        Move the thresholds and re-run the 50-claim golden set — watch the straight-through rate and the
        workflow mix change instantly. This is how an ops manager raises the auto-pay ceiling
        <em> with data</em>, not on faith.
      </p>

      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <Card>
          <CardContent className="space-y-4 p-4">
            {KNOBS.map((k) => (
              <label key={k.key} className="block text-sm">
                <div className="mb-1 flex justify-between">
                  <span>{k.label}</span>
                  <span className="font-mono text-primary">{cfg[k.key]}</span>
                </div>
                <input type="range" min={k.min} max={k.max} step={k.step} value={cfg[k.key]}
                  onChange={(e) => setCfg({ ...cfg, [k.key]: Number(e.target.value) })}
                  className="w-full accent-sky-400" />
              </label>
            ))}
            <Button onClick={run} disabled={busy} className="w-full">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Simulate
            </Button>
            <button onClick={() => setCfg(Object.fromEntries(KNOBS.map((k) => [k.key, k.def])))}
              className="w-full text-xs text-muted-foreground hover:text-foreground">reset to defaults</button>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Card><CardContent className="p-4"><div className="text-2xl font-bold">{res ? `${(res.stp_rate * 100).toFixed(0)}%` : "—"}</div><div className="text-xs text-muted-foreground">STP rate</div></CardContent></Card>
            <Card><CardContent className="p-4"><div className="text-2xl font-bold">{res ? `${(res.route_accuracy * 100).toFixed(0)}%` : "—"}</div><div className="text-xs text-muted-foreground">Route accuracy vs labels</div></CardContent></Card>
            <Card><CardContent className="p-4"><div className="text-2xl font-bold">{res?.total ?? "—"}</div><div className="text-xs text-muted-foreground">Golden claims</div></CardContent></Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Workflow mix</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {WF.map((w) => {
                const v = res?.by_workflow[w] ?? 0;
                return (
                  <div key={w} className="flex items-center gap-2 text-sm">
                    <span className="w-8 font-mono">{w}</span>
                    <div className="h-4 flex-1 rounded bg-muted">
                      <div className="h-4 rounded bg-primary" style={{ width: `${(v / maxWf) * 100}%` }} />
                    </div>
                    <span className="w-8 text-right font-mono">{v}</span>
                  </div>
                );
              })}
            </CardContent>
          </Card>
          <p className="text-xs text-muted-foreground">
            Try raising the ceiling to <span className="font-mono">$3,000</span>: the collision claims jump
            from W2 (human approval) into W1 (auto-pay) — higher STP, but you accept more auto-paid value.
          </p>
        </div>
      </div>
    </main>
  );
}

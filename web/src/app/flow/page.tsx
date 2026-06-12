"use client";

import { useState } from "react";
import Link from "next/link";
import { Loader2, Play } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Nav } from "@/components/nav";
import { FlowDiagram } from "@/components/flow-diagram";
import { agent } from "@/lib/agent";
import { useClaimDetail } from "@/lib/hooks";

interface Preset {
  name: string;
  fnol: string;
  policy?: string;
  claimant?: string;
}

const PRESETS: Preset[] = [
  {
    name: "Clean glass (→ W1)",
    fnol: "A rock hit my windshield on I-80 near Sacramento yesterday and cracked the glass. No other damage, nobody hurt. My policy number is POL-88341.",
    policy: "POL-88341", claimant: "CLMT-001",
  },
  {
    name: "Lapsed policy (→ W2 deny)",
    fnol: "A rock cracked my windshield two days ago. Nobody was hurt. Policy POL-77120. Please process my glass claim.",
    policy: "POL-77120", claimant: "CLMT-002",
  },
  {
    name: "Missing info (→ W4)",
    fnol: "Hi, I had an accident and my car is damaged. I want to file a claim. Let me know what you need.",
    claimant: "CLMT-003",
  },
  {
    name: "Fraud suspect (→ W3)",
    fnol: "My car was broken into overnight in the driveway and my laptop bag and tools were stolen from the trunk. Policy POL-55200. Open a theft claim.",
    policy: "POL-55200", claimant: "CLMT-004",
  },
];

export default function Flow() {
  const [fnol, setFnol] = useState(PRESETS[0].fnol);
  const [policy, setPolicy] = useState(PRESETS[0].policy ?? "");
  const [claimant, setClaimant] = useState(PRESETS[0].claimant ?? "");
  const [claimId, setClaimId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const detail = useClaimDetail(claimId ?? "");

  function applyPreset(p: Preset) {
    setFnol(p.fnol);
    setPolicy(p.policy ?? "");
    setClaimant(p.claimant ?? "");
  }

  async function go() {
    setBusy(true);
    setClaimId(null);
    try {
      const r = await agent.injectCustom({
        fnol_text: fnol,
        policy_number: policy || undefined,
        claimant_id: claimant || undefined,
      });
      setClaimId(r.claim_id);
    } finally {
      setTimeout(() => setBusy(false), 800);
    }
  }

  const claim = claimId ? detail?.claim : null;
  const events = claimId ? (detail?.events ?? []) : [];

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <Nav />
      <h1 className="text-2xl font-bold">Live flow</h1>
      <p className="mb-5 text-sm text-muted-foreground">
        Edit the First Notice of Loss, hit <strong>Go</strong>, and watch the agent route it across
        the architecture in real time. The LLM proposes; the deterministic spine disposes.
      </p>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        {/* input */}
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((p) => (
                <button key={p.name} onClick={() => applyPreset(p)}
                  className="rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">
                  {p.name}
                </button>
              ))}
            </div>
            <textarea value={fnol} onChange={(e) => setFnol(e.target.value)} rows={6}
              className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
              placeholder="Describe the loss…" />
            <div className="flex gap-2">
              <input value={policy} onChange={(e) => setPolicy(e.target.value)} placeholder="policy # (optional)"
                className="w-1/2 rounded border border-border bg-background px-2 py-1 text-xs" />
              <input value={claimant} onChange={(e) => setClaimant(e.target.value)} placeholder="claimant id (optional)"
                className="w-1/2 rounded border border-border bg-background px-2 py-1 text-xs" />
            </div>
            <Button onClick={go} disabled={busy || !fnol.trim()} className="w-full">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Go
            </Button>
            <p className="text-xs text-muted-foreground">
              Tip: a valid policy (POL-88341 / POL-77120 / POL-55200 / POL-90013) lets coverage
              resolve; omit it and watch it route to the information-request loop.
            </p>
          </CardContent>
        </Card>

        {/* verdict + diagram */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            {claim ? (
              <>
                <Link href={`/claims/${claim.id}`} className="font-mono text-sm text-primary hover:underline">{claim.id}</Link>
                <Badge tone={claim.state}>{claim.state}</Badge>
                {claim.workflow && <Badge>{claim.workflow}</Badge>}
                {claim.fraud_score != null && <span className="text-xs text-muted-foreground">fraud {claim.fraud_score}</span>}
                {claim.amount_est != null && <span className="text-xs text-muted-foreground">est ${claim.amount_est}</span>}
              </>
            ) : (
              <span className="text-sm text-muted-foreground">{busy ? "Injecting…" : "Edit the FNOL and press Go."}</span>
            )}
          </div>
          <FlowDiagram detail={claimId ? detail : null} />
        </div>
      </div>

      {/* live event flow */}
      {claimId && (
        <Card className="mt-6">
          <CardContent className="p-0">
            <div className="border-b border-border px-4 py-2 text-xs font-semibold uppercase text-muted-foreground">
              Information flow ({events.length} events)
            </div>
            <ul className="max-h-64 divide-y divide-border/40 overflow-y-auto font-mono text-xs">
              {[...events].reverse().map((e) => (
                <li key={e.id} className="flex items-center gap-3 px-4 py-1.5">
                  <span className="text-muted-foreground">{new Date(e.ts).toLocaleTimeString()}</span>
                  <span className="text-primary">{e.type}</span>
                  <span className="truncate text-muted-foreground">{Object.keys(e.data).length ? JSON.stringify(e.data) : ""}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

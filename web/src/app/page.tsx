"use client";

import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CAPABILITIES, litCapabilities } from "@/lib/capabilities";
import { useGlobalEvents } from "@/lib/hooks";

const SCENARIOS = [
  { title: "The 90-second settle", body: "A clean windshield claim: extract → verify → screen → pay, with zero human touch.", route: "W1" },
  { title: "The refusal", body: "A lapsed policy: the agent declines, cites the clause, and still asks a human to sign.", route: "W2" },
  { title: "The fraud catch", body: "A near-duplicate narrative + recent coverage bump: routed to SIU, no payment reachable.", route: "W3" },
];

const TRANSLATIONS = [
  ["Insurance claims", "extract → route → settle"],
  ["AP invoices", "extract → 3-way match → pay"],
  ["Inbound leads", "qualify → enrich → route"],
  ["Support tickets", "classify → resolve → escalate"],
];

export default function Landing() {
  const events = useGlobalEvents();
  const lit = litCapabilities(new Set(events.map((e) => e.type)));

  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <section className="mb-16 text-center">
        <h1 className="text-balance text-5xl font-bold tracking-tight">
          Watch an AI agent run a complete business process — live, right now.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
          Adjuster Zero is an autonomous claims department with a paper trail. The LLM proposes;
          a deterministic state machine disposes. Money never moves without a hard gate or a human
          signature — and every decision is replayable.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link href="/flow"><Button size="lg">Watch it route — live <ArrowRight className="h-4 w-4" /></Button></Link>
          <Link href="/how"><Button size="lg" variant="outline">How it works</Button></Link>
          <Link href="/analytics"><Button size="lg" variant="outline">The numbers</Button></Link>
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          100% synthetic data · ~€0/month · no login required to look around
        </p>
      </section>

      <section className="mb-16 grid gap-4 md:grid-cols-3">
        {SCENARIOS.map((s) => (
          <Card key={s.title}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                {s.title}<span className="text-xs text-muted-foreground">{s.route}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{s.body}</CardContent>
          </Card>
        ))}
      </section>

      <section className="mb-16">
        <h2 className="mb-4 text-center text-2xl font-semibold">Nine capabilities, lighting up live</h2>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
          {CAPABILITIES.map((c, i) => {
            const on = lit.has(c.key);
            return (
              <div key={c.key}
                className={`rounded-lg border px-3 py-2 text-sm transition-colors ${on ? "border-primary/50 bg-primary/10 text-foreground" : "border-border text-muted-foreground"}`}>
                <span className="mr-2 font-mono text-xs">{i + 1}</span>
                {c.label} {on && <Check className="inline h-3 w-3 text-primary" />}
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Inject a claim on the queue and watch these light up as the events arrive.
        </p>
      </section>

      <section className="mb-16">
        <h2 className="mb-4 text-center text-2xl font-semibold">Same engine, your process</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {TRANSLATIONS.map(([domain, flow]) => (
            <div key={domain} className="flex items-center justify-between rounded-lg border border-border px-4 py-3 text-sm">
              <span className="font-medium">{domain}</span>
              <span className="font-mono text-xs text-muted-foreground">{flow}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-16 rounded-lg border border-border p-6 text-sm text-muted-foreground">
        <h2 className="mb-3 text-lg font-semibold text-foreground">Honest tech summary</h2>
        <p>
          Python · FastAPI · <strong>LangGraph</strong> with a Postgres checkpointer on Cloud Run
          (scale-to-zero); Next.js on Vercel; Supabase Postgres + pgvector + Realtime; Gemini
          (flash-lite default, flash for plans/letters/tiebreaks). Deterministic routing, structural
          payment gates, an event-sourced audit log, citation-enforced coverage, and an eval gate.
          All data synthetic. Running cost: about €0/month.
        </p>
      </section>

      <section className="text-center">
        <h2 className="text-2xl font-semibold">Want this on your process?</h2>
        <p className="mt-2 text-muted-foreground">The contact form below is itself an agent. Inspect its decisions.</p>
        <div className="mt-5">
          <Link href="/contact"><Button size="lg">Talk to me <ArrowRight className="h-4 w-4" /></Button></Link>
        </div>
      </section>
    </main>
  );
}

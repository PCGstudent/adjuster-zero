"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ChevronLeft, ChevronRight, Loader2, Play, Pause, RotateCcw, Send, Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Nav } from "@/components/nav";
import { agent } from "@/lib/agent";
import type { Journey, JourneyStep, Scenario } from "@/lib/types";

const TERMINAL = ["CLOSED", "DENIED", "ESCALATED", "REVIEW_PENDING", "INFO_PENDING", "SETTLEMENT"];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const ACTOR: Record<string, { label: string; cls: string }> = {
  orchestrator: { label: "Orchestrator", cls: "bg-sky-500/15 text-sky-300 border-sky-500/40" },
  llm: { label: "LLM (proposes)", cls: "bg-violet-500/15 text-violet-300 border-violet-500/40" },
  tool: { label: "Tool", cls: "bg-amber-500/15 text-amber-300 border-amber-500/40" },
  human: { label: "Human", cls: "bg-pink-500/15 text-pink-300 border-pink-500/40" },
};

function ValueView({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "")
    return <span className="text-xs text-muted-foreground">—</span>;
  if (typeof value === "string")
    return <p className="whitespace-pre-wrap text-sm leading-relaxed">{value}</p>;
  if (typeof value === "number" || typeof value === "boolean")
    return <p className="font-mono text-sm">{String(value)}</p>;
  return (
    <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground/90">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function PhaseRail({ phases, current }: { phases: Journey["phases"]; current: string }) {
  const order = phases.map((p) => p.key);
  const curIdx = order.indexOf(current);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {phases.map((p, i) => {
        const isCur = p.key === current;
        const done = p.active && i < curIdx;
        const tone = !p.active
          ? "border-border/40 text-muted-foreground/40"
          : isCur
            ? "border-primary bg-primary/20 text-foreground"
            : done
              ? "border-primary/50 bg-primary/5 text-foreground/70"
              : "border-border text-muted-foreground";
        return (
          <div key={p.key} className="flex items-center gap-1.5">
            <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${tone} ${isCur ? "shadow-[0_0_0_3px_hsl(var(--primary)/0.15)]" : ""}`}>
              {p.label}
            </span>
            {i < phases.length - 1 && <span className="text-muted-foreground/40">→</span>}
          </div>
        );
      })}
    </div>
  );
}

export default function Walkthrough() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    agent.scenarios().then(setScenarios).catch(() => {});
  }, []);

  const steps = journey?.steps ?? [];
  const cur: JourneyStep | null = steps[step] ?? null;
  const atEnd = step >= steps.length - 1;

  const next = useCallback(() => setStep((s) => Math.min(s + 1, steps.length - 1)), [steps.length]);
  const prev = useCallback(() => setStep((s) => Math.max(s - 1, 0)), []);

  // autoplay
  const playRef = useRef(playing);
  playRef.current = playing;
  useEffect(() => {
    if (!playing) return;
    if (atEnd) { setPlaying(false); return; }
    const t = setTimeout(() => { if (playRef.current) next(); }, 2400);
    return () => clearTimeout(t);
  }, [playing, step, atEnd, next]);

  // keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev]);

  async function runScenario(key: string) {
    setBusyKey(key);
    setLoading(true);
    setPlaying(false);
    setJourney(null);
    setStep(0);
    try {
      const { claim_id } = await agent.inject(key);
      for (let i = 0; i < 45; i++) {
        await sleep(700);
        const d = await agent.claim(claim_id).catch(() => null);
        if (d && TERMINAL.includes(d.claim.state)) break;
      }
      const j = await agent.journey(claim_id);
      setJourney(j);
      setStep(0);
    } catch {
      // leave journey null; the empty state explains the agent must be reachable
    } finally {
      setLoading(false);
      setBusyKey(null);
    }
  }

  const actor = cur ? (ACTOR[cur.actor] ?? { label: cur.actor, cls: "bg-muted text-foreground border-border" }) : null;

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <Nav />
      <h1 className="text-2xl font-bold">Step-by-step — watch it think</h1>
      <p className="mb-5 max-w-3xl text-sm text-muted-foreground">
        Pick a claim and walk its life one step at a time. Each step shows its real{" "}
        <strong>input</strong>, the <strong>output</strong> it produced, and a plain-language
        explanation of <em>what happened and why</em>. This is a faithful replay of the claim&apos;s
        own audit trail — no re-running, no smoke and mirrors.
      </p>

      {/* scenario picker */}
      <Card className="mb-6">
        <CardContent className="space-y-3 p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Run a claim, then step through it
          </div>
          <div className="flex flex-wrap gap-2">
            {scenarios.map((s) => (
              <Button key={s.key} variant="outline" size="sm" disabled={loading}
                onClick={() => runScenario(s.key)}>
                {busyKey === s.key ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {s.title}
                {s.expected_route && <span className="ml-1 text-xs text-muted-foreground">→ {s.expected_route}</span>}
              </Button>
            ))}
            {scenarios.length === 0 && (
              <p className="text-sm text-muted-foreground">Agent unreachable — start it on {agent.base}.</p>
            )}
          </div>
        </CardContent>
      </Card>

      {loading && !journey && (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card/40 px-4 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" /> Running the claim end-to-end, then assembling its journey…
        </div>
      )}

      {!loading && !journey && (
        <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
          <Sparkles className="mx-auto mb-2 h-6 w-6 opacity-60" />
          Pick a claim above to begin. Tip: try the fraud and lapsed-policy ones — their journeys
          show the agent <em>refusing</em> to pay, which is the most instructive path.
        </div>
      )}

      {journey && cur && (
        <div className="space-y-4">
          {/* phase rail */}
          <Card>
            <CardContent className="space-y-3 p-4">
              <PhaseRail phases={journey.phases} current={cur.phase} />
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${((step + 1) / steps.length) * 100}%` }} />
              </div>
            </CardContent>
          </Card>

          {/* the step */}
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-muted-foreground">
                    Step {step + 1} / {steps.length}
                  </span>
                  {actor && <span className={`rounded border px-2 py-0.5 text-xs font-medium ${actor.cls}`}>{actor.label}</span>}
                  <h2 className="text-lg font-semibold">{cur.title}</h2>
                </div>
                {cur.subtitle && <span className="font-mono text-xs text-muted-foreground">{cur.subtitle}</span>}
              </div>

              {/* input → output */}
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-border bg-background/60 p-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Input · {cur.input.label}
                  </div>
                  <ValueView value={cur.input.value} />
                </div>
                <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-primary/80">
                    Output · {cur.output.label}
                  </div>
                  <ValueView value={cur.output.value} />
                </div>
              </div>

              {/* the verbatim prompt we sent to the LLM (LLM steps only) */}
              {cur.prompt && (cur.prompt.system || cur.prompt.user) && (
                <div className="rounded-lg border border-violet-500/40 bg-violet-500/5 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-violet-300">
                    <Send className="h-3.5 w-3.5" /> Prompt sent to the LLM
                  </div>
                  {cur.prompt.system && (
                    <div className="mb-2">
                      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">System instruction</div>
                      <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded bg-background/70 p-2 font-mono text-xs leading-relaxed text-foreground/90">{cur.prompt.system}</pre>
                    </div>
                  )}
                  {cur.prompt.user && (
                    <div>
                      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">User message</div>
                      <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded bg-background/70 p-2 font-mono text-xs leading-relaxed text-foreground/90">{cur.prompt.user}</pre>
                    </div>
                  )}
                </div>
              )}

              {/* explanation */}
              <div className="rounded-lg border border-border bg-card/40 p-3">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  What happened &amp; why
                </div>
                <p className="text-sm leading-relaxed">{cur.explanation}</p>
              </div>

              {/* controls */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={prev} disabled={step === 0}>
                    <ChevronLeft className="h-4 w-4" /> Prev
                  </Button>
                  <Button size="sm" onClick={next} disabled={atEnd}>
                    Next <ChevronRight className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setPlaying((p) => !p)} disabled={atEnd}>
                    {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                    {playing ? "Pause" : "Auto-play"}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => { setStep(0); setPlaying(false); }}>
                    <RotateCcw className="h-4 w-4" /> Restart
                  </Button>
                </div>
                <span className="text-xs text-muted-foreground">← / → to navigate</span>
              </div>
            </CardContent>
          </Card>

          {/* outcome banner at the end */}
          {atEnd && (
            <Card>
              <CardContent className="flex flex-wrap items-center gap-3 p-4 text-sm">
                <span className="font-semibold">Outcome:</span>
                <Badge tone={journey.final.state ?? ""}>{journey.final.state}</Badge>
                {journey.final.workflow && <Badge>{journey.final.workflow}</Badge>}
                {journey.final.rule_id && <span className="text-muted-foreground">rule {journey.final.rule_id}</span>}
                {journey.final.fraud_score != null && <span className="text-muted-foreground">fraud {journey.final.fraud_score}</span>}
                <Link href={`/claims/${journey.claim_id}`} className="ml-auto font-mono text-xs text-primary hover:underline">
                  open full claim →
                </Link>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </main>
  );
}

"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, ChevronRight, Wrench, GitBranch, Brain, CircleDot } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { agent } from "@/lib/agent";
import { useClaimDetail } from "@/lib/hooks";
import type { AgentDecision, ClaimEvent, ToolCall } from "@/lib/types";

const EVENT_LABEL: Record<string, string> = {
  "claim.received": "Claim received",
  "claim.extracted": "Fields extracted from FNOL",
  "claim.classified": "Claim classified",
  "claim.investigated": "Investigation complete",
  "claim.routed": "Routed to a workflow",
  "claim.executing": "Executing the plan",
  "claim.settled": "Settlement booked",
  "claim.closed": "Claim closed",
  "claim.parked": "Parked for human review",
  "claim.escalated": "Escalated to a human",
};

const TOOL_LABEL: Record<string, string> = {
  policy_lookup: "Looked up the policy",
  coverage_check: "Checked coverage",
  repair_cost_estimator: "Estimated repair cost",
  reserve_set: "Set the financial reserve",
  payment_execute: "Paid the claim automatically",
  customer_comm_send: "Drafted a customer letter",
};

type Item = {
  ts: string;
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  json?: unknown;
};

function Json({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  if (value == null) return null;
  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`} />
        details
      </button>
      {open && (
        <pre className="mt-1 overflow-x-auto rounded bg-muted/40 p-2 text-xs">
          {JSON.stringify(value, null, 2)}
        </pre>
      )}
    </div>
  );
}

function buildItems(events: ClaimEvent[], tools: ToolCall[], decisions: AgentDecision[]): Item[] {
  const items: Item[] = [];
  for (const e of events) {
    let subtitle: string | undefined;
    if (e.type === "claim.routed") subtitle = `${e.data.workflow} — rule ${e.data.rule_id}`;
    if (e.type === "claim.parked") subtitle = String(e.data.reason ?? "");
    items.push({
      ts: e.ts,
      icon: <CircleDot className="h-4 w-4 text-sky-400" />,
      title: EVENT_LABEL[e.type] ?? e.type,
      subtitle,
      json: Object.keys(e.data).length ? e.data : undefined,
    });
  }
  for (const t of tools) {
    items.push({
      ts: t.ts,
      icon: <Wrench className="h-4 w-4 text-emerald-400" />,
      title: TOOL_LABEL[t.tool] ?? t.tool,
      subtitle: `${t.status}${t.cached ? " (cached)" : ""}${t.latency_ms ? ` · ${t.latency_ms}ms` : ""} · T${t.risk_tier}`,
      json: { args: t.args, result: t.result, error: t.error_code },
    });
  }
  for (const d of decisions) {
    const icon =
      d.decision_type === "route" ? (
        <GitBranch className="h-4 w-4 text-amber-400" />
      ) : (
        <Brain className="h-4 w-4 text-violet-400" />
      );
    const subtitle =
      d.decision_type === "route"
        ? `rule ${d.rule_id}`
        : `${d.model ?? ""}${d.confidence != null ? ` · conf ${d.confidence}` : ""}`;
    items.push({ ts: d.ts, icon, title: `Decision: ${d.decision_type}`, subtitle, json: d.output });
  }
  return items.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
}

export default function ClaimPage() {
  const params = useParams<{ id: string }>();
  const detail = useClaimDetail(params.id);

  if (!detail) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-10">
        <Link href="/" className="flex items-center gap-1 text-sm text-primary">
          <ArrowLeft className="h-4 w-4" /> Queue
        </Link>
        <p className="mt-8 text-muted-foreground">Loading claim {params.id}…</p>
      </main>
    );
  }

  const { claim } = detail;
  const items = buildItems(detail.events, detail.tool_calls, detail.decisions);

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <Link href="/" className="flex items-center gap-1 text-sm text-primary">
        <ArrowLeft className="h-4 w-4" /> Queue
      </Link>

      <header className="my-4 flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-2xl font-bold">{claim.id}</h1>
        <Badge tone={claim.state}>{claim.state}</Badge>
        {claim.workflow && <Badge>{claim.workflow}</Badge>}
        <span className="text-sm text-muted-foreground">
          {claim.line ?? "—"}/{claim.peril ?? "—"} · conf {claim.confidence ?? "—"} · fraud{" "}
          {claim.fraud_score ?? "—"}
        </span>
        {claim.state === "INFO_PENDING" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              agent.submitDocuments(claim.id, {
                policy_number: "POL-90013",
                loss_date: "2026-06-05",
                loss_location: "Main St",
              })
            }
          >
            Simulate document upload
          </Button>
        )}
      </header>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-[260px_1fr]">
        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Claim facts</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <Fact label="Policy" value={claim.policy_id} />
              <Fact label="Claimant" value={claim.claimant_id} />
              <Fact label="Completeness" value={claim.completeness} />
              <Fact label="Estimate" value={claim.amount_est != null ? `$${claim.amount_est}` : null} />
              <Fact label="Reserve" value={claim.reserve != null ? `$${claim.reserve}` : null} />
              <Fact label="Paid" value={claim.paid != null ? `$${claim.paid}` : null} />
            </CardContent>
          </Card>
        </aside>

        <section>
          <Card>
            <CardHeader>
              <CardTitle>Execution timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3">
                {items.map((it, i) => (
                  <li key={i} className="flex gap-3">
                    <div className="mt-0.5">{it.icon}</div>
                    <div className="flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-medium">{it.title}</span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {new Date(it.ts).toLocaleTimeString()}
                        </span>
                      </div>
                      {it.subtitle && (
                        <div className="text-xs text-muted-foreground">{it.subtitle}</div>
                      )}
                      <Json value={it.json} />
                    </div>
                  </li>
                ))}
                {items.length === 0 && (
                  <p className="text-sm text-muted-foreground">Waiting for the agent…</p>
                )}
              </ol>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}

function Fact({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex justify-between border-b border-border/40 py-1 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">{value ?? "—"}</span>
    </div>
  );
}

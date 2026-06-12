"use client";

import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Nav } from "@/components/nav";
import { useGlobalEvents } from "@/lib/hooks";

const TYPE_COLOR: Record<string, string> = {
  "claim.received": "text-slate-300",
  "claim.routed": "text-amber-300",
  "claim.settled": "text-emerald-300",
  "claim.closed": "text-emerald-400",
  "claim.escalated": "text-red-300",
  "claim.denied": "text-red-300",
  "approval.requested": "text-violet-300",
  "approval.resolved": "text-violet-300",
  "control.degraded_mode": "text-orange-300",
  "tool.completed": "text-sky-300",
};

export default function Console() {
  const events = useGlobalEvents();
  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <Nav />
      <h1 className="mb-1 text-2xl font-bold">Agent console</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Live event stream across all claims (mission control). {events.length} recent events.
      </p>
      <Card>
        <CardContent className="p-0">
          <ul className="divide-y divide-border/40 font-mono text-xs">
            {events.map((e) => (
              <li key={e.id} className="flex items-center gap-3 px-4 py-1.5">
                <span className="text-muted-foreground">
                  {new Date(e.ts).toLocaleTimeString()}
                </span>
                <Link href={`/claims/${e.claim_id}`} className="text-primary hover:underline">
                  {e.claim_id}
                </Link>
                <span className={TYPE_COLOR[e.type] ?? "text-foreground"}>{e.type}</span>
                <span className="truncate text-muted-foreground">
                  {Object.keys(e.data).length ? JSON.stringify(e.data) : ""}
                </span>
              </li>
            ))}
            {events.length === 0 && (
              <li className="px-4 py-8 text-center text-muted-foreground">No events yet.</li>
            )}
          </ul>
        </CardContent>
      </Card>
    </main>
  );
}

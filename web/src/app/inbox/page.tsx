"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, Pencil, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Nav } from "@/components/nav";
import { agent } from "@/lib/agent";
import { useApprovals } from "@/lib/hooks";
import type { Approval } from "@/lib/types";

function actionSummary(a: Approval): string {
  const act = a.requested_action;
  if (act.type === "pay") return `Pay $${act.amount?.toLocaleString()} to ${act.payee_id ?? "claimant"}`;
  if (act.type === "deny") return `Deny the claim — ${act.reason ?? "see record"}`;
  return act.type;
}

function ApprovalCard({ a, onResolved }: { a: Approval; onResolved: () => void }) {
  const [modify, setModify] = useState(false);
  const [amount, setAmount] = useState(a.requested_action.amount ?? 0);
  const [reason, setReason] = useState("depreciation");
  const [busy, setBusy] = useState(false);

  async function resolve(resolution: string, extra?: object) {
    setBusy(true);
    try {
      await agent.resolve(a.id, { resolution, ...extra });
      setTimeout(onResolved, 400);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <Link href={`/claims/${a.claim_id}`} className="font-mono text-primary hover:underline">
            {a.claim_id}
          </Link>
          <Badge>{a.requested_action.type === "deny" ? "Denial" : "Payout"}</Badge>
        </div>
        <p className="text-sm">{actionSummary(a)}</p>
        <p className="text-xs text-muted-foreground">
          confidence {a.confidence ?? "—"} · risk tier T{a.risk_tier}
        </p>

        {modify ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs">
              New amount
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="ml-2 w-28 rounded border border-border bg-background px-2 py-1"
              />
            </label>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="rounded border border-border bg-background px-2 py-1 text-xs"
            >
              <option value="depreciation">depreciation</option>
              <option value="policy_limit">policy limit</option>
              <option value="duplicate_charge">duplicate charge</option>
            </select>
            <Button
              size="sm"
              disabled={busy}
              onClick={() => resolve("modify", { delta: { amount }, reason_code: reason })}
            >
              Save & settle
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setModify(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => resolve("approve")}>
              <Check className="h-4 w-4" /> Approve
            </Button>
            {a.requested_action.type === "pay" && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => setModify(true)}>
                <Pencil className="h-4 w-4" /> Modify
              </Button>
            )}
            <Button
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={() => resolve("reject", { reason_code: "needs_senior_review" })}
            >
              <X className="h-4 w-4" /> Reject
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function Inbox() {
  const { approvals, refresh } = useApprovals();
  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <Nav />
      <h1 className="mb-1 text-2xl font-bold">Approval inbox</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        {approvals.length} pending. Approve / Modify / Reject resumes the paused claim
        (durable interrupt + checkpointer).
      </p>
      <div className="space-y-4">
        {approvals.map((a) => (
          <ApprovalCard key={a.id} a={a} onResolved={refresh} />
        ))}
        {approvals.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing pending — the agent is keeping up.</p>
        )}
      </div>
    </main>
  );
}

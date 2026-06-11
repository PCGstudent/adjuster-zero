"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getSupabase, supabaseConfigured } from "@/lib/supabase";

type Status = "checking" | "ok" | "down";

function Dot({ status }: { status: Status }) {
  if (status === "checking") return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />;
  if (status === "ok") return <CheckCircle2 className="h-4 w-4 text-primary" />;
  return <XCircle className="h-4 w-4 text-destructive" />;
}

function StatusRow({ label, status, detail }: { label: string; status: Status; detail?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 last:border-0">
      <span className="text-sm">{label}</span>
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        {detail} <Dot status={status} />
      </span>
    </div>
  );
}

export default function Home() {
  const [supabase, setSupabase] = useState<Status>("checking");
  const [agent, setAgent] = useState<Status>("checking");
  const [agentDetail, setAgentDetail] = useState<string>();

  useEffect(() => {
    // Supabase: a trivial read (count claims). RLS allows public SELECT.
    (async () => {
      if (!supabaseConfigured) return setSupabase("down");
      const sb = getSupabase();
      if (!sb) return setSupabase("down");
      const { error } = await sb.from("claims").select("id", { count: "exact", head: true });
      setSupabase(error ? "down" : "ok");
    })();

    // Agent service /healthz
    (async () => {
      const base = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8080";
      try {
        const res = await fetch(`${base}/healthz`, { cache: "no-store" });
        const body = await res.json();
        setAgent(res.ok ? "ok" : "down");
        setAgentDetail(body?.db_reachable ? "db reachable" : "db unconfigured");
      } catch {
        setAgent("down");
      }
    })();
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <header>
        <h1 className="text-5xl font-bold tracking-tight">Adjuster Zero</h1>
        <p className="mt-3 text-lg text-muted-foreground">
          An autonomous claims department with a paper trail.
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          🚧 Building in public — Phase 0 (foundations).
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>System status</CardTitle>
        </CardHeader>
        <CardContent>
          <StatusRow label="Supabase (Postgres + Realtime)" status={supabase} />
          <StatusRow label="Agent service (/healthz)" status={agent} detail={agentDetail} />
        </CardContent>
      </Card>
    </main>
  );
}

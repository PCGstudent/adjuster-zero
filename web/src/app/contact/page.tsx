"use client";

import { useState } from "react";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Nav } from "@/components/nav";
import { agent } from "@/lib/agent";

interface Result {
  qualified: boolean;
  clarifying_question: string | null;
  email_draft: string;
  decisions: { step: string; result: string; why?: string }[];
}

export default function Contact() {
  const [form, setForm] = useState({ name: "", email: "", message: "", process: "" });
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      setResult((await agent.contact(form)) as unknown as Result);
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <Nav />
      <h1 className="text-2xl font-bold">Talk to me</h1>
      <p className="mb-6 mt-1 flex items-center gap-2 text-sm text-muted-foreground">
        <Bot className="h-4 w-4" /> Yes — this contact form is also an agent. Submit it and inspect
        its decisions below.
      </p>

      <Card>
        <CardContent className="space-y-3 p-4">
          <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
            placeholder="Your name" value={form.name} onChange={set("name")} />
          <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
            placeholder="Email" value={form.email} onChange={set("email")} />
          <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
            placeholder="Which process? (claims / invoices / leads / tickets)" value={form.process} onChange={set("process")} />
          <textarea className="h-24 w-full rounded border border-border bg-background px-3 py-2 text-sm"
            placeholder="What would you like to automate?" value={form.message} onChange={set("message")} />
          <Button onClick={submit} disabled={busy}>{busy ? "Thinking…" : "Send"}</Button>
        </CardContent>
      </Card>

      {result && (
        <Card className="mt-6">
          <CardHeader><CardTitle>The contact agent&apos;s decisions</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <ol className="space-y-1">
              {result.decisions.map((d, i) => (
                <li key={i} className="border-b border-border/30 py-1 last:border-0">
                  <span className="font-medium">{d.step}</span> → {d.result}
                  {d.why && <span className="text-xs text-muted-foreground"> ({d.why})</span>}
                </li>
              ))}
            </ol>
            {result.clarifying_question && (
              <p className="text-amber-300">Clarifying question: {result.clarifying_question}</p>
            )}
            <div>
              <div className="mb-1 text-xs uppercase text-muted-foreground">Drafted email to the owner</div>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted/40 p-3 text-xs">{result.email_draft}</pre>
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

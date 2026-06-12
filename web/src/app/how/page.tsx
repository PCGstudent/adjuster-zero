import Link from "next/link";
import { Nav } from "@/components/nav";
import { ArchitectureDiagram } from "@/components/architecture-diagram";

export const metadata = { title: "Adjuster Zero — How it works" };

const ACTORS: Record<string, { label: string; cls: string }> = {
  det: { label: "Deterministic", cls: "bg-sky-500/15 text-sky-300" },
  lite: { label: "LLM · flash-lite", cls: "bg-indigo-500/15 text-indigo-300" },
  flash: { label: "LLM · flash", cls: "bg-violet-500/15 text-violet-300" },
  rag: { label: "RAG", cls: "bg-emerald-500/15 text-emerald-300" },
  human: { label: "Human", cls: "bg-rose-500/15 text-rose-300" },
};

function Tag({ a }: { a: keyof typeof ACTORS }) {
  return <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${ACTORS[a].cls}`}>{ACTORS[a].label}</span>;
}

interface Step {
  n: string;
  title: string;
  actors: (keyof typeof ACTORS)[];
  what: string;
  guardrail: string;
}

const STEPS: Step[] = [
  {
    n: "0", title: "Intake — the FNOL arrives", actors: ["det"],
    what: "A First Notice of Loss comes in (email, web form, or API). The intake layer normalizes it into a Claim Aggregate (the agent's working memory), assigns a claim_id + trace_id, stores documents, and emits the first event. There is deliberately no LLM here.",
    guardrail: "Dumb on purpose: garbage input fails loudly before it reaches the expensive layers. Every later step carries the trace_id so one query reconstructs the whole claim.",
  },
  {
    n: "1", title: "Extract — text → typed fields", actors: ["lite"],
    what: "flash-lite reads the FNOL and returns structured fields (policy number, loss date, peril, …) with a per-field confidence and a completeness score, plus a list of missing required fields.",
    guardrail: "The output is validated against a Pydantic schema. On a schema violation the validator errors are fed back for exactly ONE repair attempt, then the claim escalates. No silent retries, no unbounded loops.",
  },
  {
    n: "2", title: "Classify — line / peril / severity", actors: ["lite"],
    what: "flash-lite classifies the claim (auto/property/injury, peril, severity 1–5, complexity, injury/attorney flags) and returns alternative labels with probabilities.",
    guardrail: "If the top-2 margin is small it lowers its own confidence rather than guessing. Confidence becomes a routing input — it never silently picks a label.",
  },
  {
    n: "3", title: "Investigate — gather the facts (agentic RAG + fraud)", actors: ["det", "rag", "flash", "lite"],
    what: "The orchestrator runs read-only tools to assemble the routing inputs: policy lookup, a rules coverage pre-screen, a hybrid RAG retrieval over the guideline corpus, an LLM coverage determination grounded in the retrieved chunks (with required citations), a repair-cost estimate, claim history, exact + semantic duplicate detection, an LLM narrative-plausibility screen, a mandatory sanctions screen, and a fraud score with itemized signals.",
    guardrail: "This is where RAG is used the hard way — as grounding for a consequential decision, not a search box. Coverage with < 100% citation coverage is confidence-floored to 0.5 and forced to human review. If a fraud control is down, routing is capped at W2 (no straight-through).",
  },
  {
    n: "4", title: "Route — the decision engine", actors: ["det", "flash"],
    what: "A pure, unit-tested function evaluates the rule table R-00..R-99 top-down over the typed inputs and business facts, with thresholds read from a versioned config row. It returns the workflow + the rule that fired. Only the ambiguous fraud band (R-06) calls the LLM to break the tie, grounded in guidelines and logged with alternatives.",
    guardrail: "Routing is policy, not vibes: no I/O, no clock, no randomness in the function. rule_id + config_version are recorded on every decision, so any historical routing is replayable against a new rule table before it ships.",
  },
  {
    n: "5", title: "Execute — the workflow runs (the state machine)", actors: ["det", "flash", "human"],
    what: "The executor walks the routed workflow. W1 reserves, screens sanctions, pays via a tier-0 policy gate, drafts the settlement letter, and closes. W2 proposes a payout or a drafted denial, then pauses for a human (approve / modify / reject). W3 hands off to SIU. W4 requests documents and parks. W5 prepares a packet for a senior adjuster.",
    guardrail: "payment_execute cannot be constructed without an authorization carrying a policy-gate or approval reference — an ungated payment is unrepresentable. W3/W4/W5 have no payment edge at all. Max 2 replans and a per-claim token budget bound the work.",
  },
  {
    n: "6", title: "Pause & resume — human-in-the-loop", actors: ["human", "det"],
    what: "When a workflow needs a human, it calls interrupt(); the graph state is checkpointed to Postgres and the run stops. The approval inbox shows the request with evidence, confidence and alternatives. Resolving it resumes the graph from exactly where it paused.",
    guardrail: "A paused claim costs nothing and survives an agent-service restart (state lives in the checkpointer, not memory). This is the durable analogue of Step Functions waitForTaskToken. A Modify captures a structured delta + reason code — the override data behind the calibration chart.",
  },
  {
    n: "7", title: "Record — every step is an event", actors: ["det"],
    what: "Each transition writes a claim_events row in the same transaction as the projection update, and each decision/tool call is a first-class persisted entity with confidence, alternatives, citations, tokens and latency. The dashboard consumes these via Supabase Realtime.",
    guardrail: "The event IS the transition (event-sourced). The audit trail, the live dashboard feed, and the replay/eval substrate are one mechanism, not three features.",
  },
];

const CONCEPTS: { title: string; body: string }[] = [
  {
    title: "Agentic — not a RAG chatbot",
    body: "A RAG bot answers; it never acts, so it never needs idempotency, compensation, approval gates, or an audit trail, and its worst failure is a wrong sentence. This is an agent: it routes across five workflows, calls risk-tiered tools with real consequences, maintains durable state, pauses for humans, and conditionally moves money under audit. RAG is one subsystem among many — used as grounding for decisions, with enforced citations.",
  },
  {
    title: "The LLM proposes, the orchestrator disposes",
    body: "Every LLM output is Pydantic-validated data — a classification, a draft, a proposed plan. It never triggers a side effect directly. A deterministic state machine routes, gates, executes and compensates. Knowing exactly what to delegate to a probabilistic component and what to keep deterministic is the whole point.",
  },
  {
    title: "Structured output, one repair, then escalate",
    body: "Schema-violation rate is the cheapest honest model-quality signal. Every call uses a response schema and is validated; one repair retry feeds the validator errors back; a second failure escalates. Never a third attempt.",
  },
  {
    title: "Agentic RAG with enforced citations",
    body: "Coverage and denial determinations must cite retrieved guideline chunk IDs. A validator computes citation coverage; an uncited determinative claim is confidence-floored to 0.5, which the router turns into mandatory human review. A 'citation' to a low-relevance chunk is treated as uncited.",
  },
  {
    title: "Risk tiers, enforced by construction",
    body: "T0 read-only, T1 reversible writes, T2 money / external comms. A T2 payment requires an authorization object that itself requires a policy-gate or human-approval reference — so the invalid call cannot be built, not merely rejected at runtime. Safety by construction beats safety by prompt.",
  },
  {
    title: "Fail-closed compliance & compensation",
    body: "If the sanctions service is unavailable, all payments are blocked globally — a stuck claim beats an unscreened payout. A failed or blocked payment triggers a compensation saga: the reserve is restored and the claim returns to human review. Payments are idempotent and reconcile before any retry.",
  },
  {
    title: "Bounded autonomy",
    body: "Max two replans per claim and a per-claim token budget, enforced by the executor. Budget exhaustion escalates to a human — that is correct behavior, not a failure. A runaway re-plan loop is a cost incident, so it cannot happen.",
  },
  {
    title: "Evals as a gate",
    body: "Fifty labeled golden claims replay through the real graph and produce a route confusion matrix + pass rate. Prompt and rule changes ship behind this gate or not at all.",
  },
];

const MAPPING: [string, string, string][] = [
  ["Step Functions + waitForTaskToken", "LangGraph + PostgresSaver + interrupt()", "durable state machine, HITL"],
  ["DynamoDB single-table", "Supabase Postgres (relational)", "decisions/tools/approvals as entities"],
  ["EventBridge bus", "claim_events + Supabase Realtime", "event-sourcing, live cockpit"],
  ["OpenSearch", "pgvector (hybrid FTS + kNN)", "RAG with citations"],
  ["Bedrock", "Gemini (response_schema = validation)", "typed outputs, one repair"],
  ["CloudWatch + X-Ray", "LangSmith + our decision log", "end-to-end trace_id"],
  ["Cognito", "Supabase Auth + RLS", "auth, viewer/operator roles"],
];

const NOT_ALLOWED = [
  "Trigger any side effect directly — its output is always validated data first.",
  "Own routing — a pure, versioned, unit-tested rule function does (the LLM only breaks the R-06 tie, logged).",
  "Execute a payment or send a customer comm without a structural gate (policy-gate or approval ref).",
  "Loop unbounded — max 2 replans and a per-claim token budget, enforced by the executor.",
  "Make a coverage call without citing the guidelines that support it.",
];

export default function How() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <Nav />
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">How it works</h1>
        <p className="mt-2 max-w-3xl text-muted-foreground">
          Every step that happens when a claim arrives — and exactly who does what. The LLM
          proposes (extracts, classifies, drafts, grounds); a deterministic state machine disposes
          (routes, gates, executes, compensates). Try it live on the{" "}
          <Link href="/flow" className="text-primary hover:underline">flow page</Link>.
        </p>
      </header>

      <ArchitectureDiagram />

      <section className="mt-10">
        <h2 className="mb-4 text-xl font-semibold">The pipeline, step by step</h2>
        <ol className="space-y-4">
          {STEPS.map((s) => (
            <li key={s.n} className="rounded-lg border border-border bg-card p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">{s.n}</span>
                <h3 className="text-base font-semibold">{s.title}</h3>
                <span className="flex gap-1">{s.actors.map((a) => <Tag key={a} a={a} />)}</span>
              </div>
              <p className="text-sm text-muted-foreground">{s.what}</p>
              <p className="mt-2 text-sm"><span className="font-semibold text-foreground">Guardrail: </span><span className="text-muted-foreground">{s.guardrail}</span></p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-10">
        <h2 className="mb-4 text-xl font-semibold">The concepts behind it</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {CONCEPTS.map((c) => (
            <div key={c.title} className="rounded-lg border border-border bg-card p-4">
              <h3 className="mb-1 font-semibold">{c.title}</h3>
              <p className="text-sm text-muted-foreground">{c.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="mb-3 text-xl font-semibold">What the LLM is <span className="text-rose-300">not</span> allowed to do</h2>
        <ul className="space-y-2">
          {NOT_ALLOWED.map((t) => (
            <li key={t} className="flex gap-2 rounded-lg border border-rose-500/20 bg-rose-500/5 px-4 py-2 text-sm">
              <span className="text-rose-300">✕</span><span className="text-muted-foreground">{t}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10">
        <h2 className="mb-3 text-xl font-semibold">Same patterns, two stacks (AWS ↔ zero-cost)</h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/30 text-left text-xs uppercase text-muted-foreground">
              <tr><th className="px-4 py-2">Production (AWS)</th><th className="px-4 py-2">Live (zero-cost)</th><th className="px-4 py-2">Pattern preserved</th></tr>
            </thead>
            <tbody>
              {MAPPING.map(([a, b, c]) => (
                <tr key={a} className="border-t border-border/50">
                  <td className="px-4 py-2 text-muted-foreground">{a}</td>
                  <td className="px-4 py-2">{b}</td>
                  <td className="px-4 py-2 text-muted-foreground">{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="mt-10 text-center text-sm text-muted-foreground">
        Watch it happen on a real claim → <Link href="/flow" className="text-primary hover:underline">Live flow</Link>
        {"  ·  "}<Link href="/queue" className="text-primary hover:underline">Claims queue</Link>
        {"  ·  "}
        <a href="https://github.com/PCGstudent/adjuster-zero/blob/main/docs/MANUAL.md"
          target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
          Full written manual (GitHub)
        </a>
      </p>
    </main>
  );
}

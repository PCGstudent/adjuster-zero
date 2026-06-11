# Adjuster Zero

> **An autonomous insurance-claims operations agent.** It ingests a First Notice
> of Loss, extracts and verifies it against policy systems, routes it across five
> workflows (straight-through payment, standard adjudication, fraud investigation,
> information request, high-severity escalation) via a deterministic, replayable
> rule engine fed by LLM classification; executes investigation and settlement
> through 18 risk-tiered, schema-validated tools orchestrated by a durable state
> machine; pays small clean claims with zero human touch and pauses for human
> approval everywhere else; and records every decision — confidence, alternatives,
> citations, overrides — in an event-sourced audit log rendered live on a
> transparent operations dashboard.

🚧 **Building in public.** All data is 100% synthetic. Running cost: ~€0/month.

The opinionated stance that makes this a portfolio signal rather than a demo:
**the LLM never owns control flow.** The LLM proposes (plans, classifications,
drafts); a deterministic state machine disposes (routes, gates, executes,
compensates). Money never moves without a hard-coded policy tier or a human
signature. Every decision is replayable from an append-only event log.

## Stack (live, zero-cost profile)

| Layer | Choice |
|---|---|
| Agent service | Python 3.12 · FastAPI · **LangGraph** (`PostgresSaver`) · Cloud Run (scale-to-zero) |
| LLM | Gemini `2.5-flash-lite` (default) / `2.5-flash` (plan, R-06 tiebreak, letters) via `google-genai` |
| Data | Supabase Postgres · pgvector · pg_cron · Auth (RLS) · Realtime · Storage |
| Web | Next.js 15 · Tailwind · shadcn/ui · Vercel Hobby |
| Observability | LangSmith (env-gated) + our own decision log |
| CI / cron | GitHub Actions (lint, tests, weekly evals, daily keep-alive) |

The AWS "production profile" (Part 5 of the blueprint) and the **AWS↔zero-cost
mapping table** are documented in `docs/` — the same patterns, two
implementations.

## Repository layout

```
/agent   FastAPI + LangGraph service (uv project)
/web     Next.js dashboard + showroom
/db      SQL migrations (numbered), seeds, RLS, guidelines
/evals   golden claim set + runner + reports
/docs    blueprint.md, zero-cost-plan.md, DECISIONS.md, deploy.md
```

## Quick start (local)

```bash
# 1. Apply the DB schema to your Supabase project — see db/README.md
# 2. Copy env template and fill in keys (never commit .env)
cp .env.example .env
cp .env.example web/.env.local

# 3. Agent (http://localhost:8080)
cd agent && uv sync --extra dev && uv run uvicorn adjuster_zero.main:app --reload --port 8080

# 4. Web (http://localhost:3000)
cd web && npm install && npm run dev
```

Tests / lint / typecheck: `make test`, `make lint`, `make typecheck`
(or run the underlying `uv run …` / `npm run …` commands on Windows).

## What the LLM is **NOT** allowed to do

- Trigger any side effect directly (its output is always validated data first).
- Own routing (a pure, versioned, unit-tested rule function does — the LLM only
  breaks the R-06 ambiguous band, and that tiebreak is logged with alternatives).
- Execute a payment or send a customer comm without a structural gate
  (`approval_ref` / `policy_gate_ref`) — the ungated call is unrepresentable.
- Loop unbounded: max 2 replans and a per-claim token budget, enforced by the
  executor; exhaustion escalates to a human.

See `docs/blueprint.md` for the full spec and `docs/DECISIONS.md` for the ADR log.

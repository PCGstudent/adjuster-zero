# CLAUDE.md — Adjuster Zero

## What this project is

Adjuster Zero is an autonomous insurance-claims operations agent built as a **public portfolio showroom**: it demonstrates production-grade agentic architecture (workflow routing, dynamic tool calling, durable state, human-in-the-loop, observability, evals) live, at ~€0/month running cost. The audience is technical hiring managers and prospective consulting clients. All synthetic data — never real PII.

**Source of truth** (read before planning any phase):
- `docs/blueprint.md` — full product/architecture spec (workflows W1–W5, routing rules R-00..R-99, 18 tools, DB schema, observability, roadmap).
- `docs/zero-cost-plan.md` — the zero-cost execution stack and constraints (in Portuguese; binding).
- `docs/DECISIONS.md` — running ADR log. Append, never rewrite history.

If this file and the docs conflict, this file wins. If anything is ambiguous, ask the human — do not guess on architecture.

## Non-negotiable architecture theses

1. **The LLM proposes; the orchestrator disposes.** LLM outputs are data (Pydantic-validated). No LLM output ever triggers a side effect directly. Never use framework "auto" tool-calling loops for T1/T2 actions.
2. **Routing is deterministic.** A pure, unit-tested function implements rules R-00..R-99 over typed inputs, reading thresholds from the `config` table (hot-reload). The LLM is invoked only for the R-06 ambiguous band, and that decision is persisted with alternatives and rationale.
3. **Every LLM call uses structured output** validated against a schema. On validation failure: exactly one repair retry (feed validator errors back), then `escalate_to_human`. No silent retries, no unbounded loops.
4. **Risk tiers are structural, not behavioral.** T0 = read-only. T1 = reversible writes inside a validated plan. T2 (`payment_execute`, `customer_comm_send` in send mode) requires `approval_ref` or `policy_gate_ref` — make it a required constructor/field so the invalid call is unrepresentable, not merely checked at runtime.
5. **Event-sourced core.** Every state transition writes a row to `claim_events` (the event IS the transition). The dashboard consumes events via Supabase Realtime. The claim aggregate is a projection.
6. **Bounded autonomy.** Max 2 replans per claim. Per-claim token budget enforced by the executor. Budget exhaustion → escalate (that is correct behavior, not failure).
7. **Fail closed on controls.** Sanctions check unavailable ⇒ all payments blocked. Any fraud control degraded ⇒ route cap at W2 (no straight-through processing).
8. **Citations are enforced.** Coverage/denial determinations must cite retrieved guideline chunk IDs; citation coverage < 100% on determinative claims ⇒ confidence floored to 0.5 ⇒ human review.
9. **Everything observable.** Decisions, tool calls, approvals, and overrides are first-class persisted entities with confidence, alternatives, citations, latency, and tokens — not log lines.

## Fixed stack (do not substitute)

- **Agent service:** Python 3.12, `uv`, FastAPI, LangGraph with `PostgresSaver` checkpointer, Pydantic v2. Container deployed to Google Cloud Run (scale-to-zero).
- **LLM:** Gemini via the `google-genai` SDK. `gemini-2.5-flash-lite` is the default (extraction, classification, fraud signals); `gemini-2.5-flash` only for planning, R-06 tiebreaks, and customer letters. Structured outputs via `response_schema`. Embeddings: `gemini-embedding-001`.
- **Data:** Supabase Postgres (schema = blueprint Part 6 relational DDL) + pgvector + pg_cron. Supabase Auth (roles: operator, viewer) with RLS. Supabase Storage for documents. Supabase Realtime for the live timeline.
- **Web:** Next.js 15 (App Router, TypeScript), Tailwind, shadcn/ui, deployed on Vercel Hobby.
- **Observability:** LangSmith tracing (env-gated, optional) + our own decision log. **CI/cron:** GitHub Actions (lint, tests, weekly evals, daily keep-alive ping for Supabase + Cloud Run).

## Free-tier rules (cost is a feature)

- All Gemini calls go through one `GeminiClient` wrapper: token-bucket rate limiter (assume 10 RPM flash / 15 RPM flash-lite), persisted daily request counters (RPD budget), 429 → exponential backoff → automatic downgrade flash→flash-lite → visible "rate-limited, retrying" event on the claim timeline.
- Never call the LLM inside an unbounded loop. Cache tool results by content hash where marked cacheable in the blueprint.
- No paid services, no NAT, no VPC, no always-on instances. If a step seems to need one, stop and ask.

## Repository layout

```
/agent      FastAPI + LangGraph service (uv project)
/web        Next.js dashboard + showroom
/db         SQL migrations (numbered), seeds, RLS policies
/evals      golden claim set (JSON) + runner + reports
/docs       blueprint.md, zero-cost-plan.md, DECISIONS.md, demo-script.md
/.claude    agents/ (subagents), settings
/.github    workflows/ (ci.yml, evals.yml, keepalive.yml)
Makefile    dev, test, demo, seed, evals targets
```

## Conventions

- **All repo content in English** (code, comments, README, UI copy) — international reviewers will read it. Conversation with the human may be in Portuguese.
- Type everything: Pydantic v2 models for all LLM I/O, tool args/results, events. `ruff` + `mypy` clean; `pytest` for the router, tool registry validation, idempotency, and budget gates (these tests are the portfolio).
- Conventional commits, small and frequent. Never commit secrets; maintain `.env.example`.
- UI: claims-domain words in plain language ("Pay automatically", not "STP"); JSON details behind expanders; the glass-cockpit timeline is the hero surface.

## Process rules (how we work together)

1. **Plan first, always.** At the start of every phase, enter plan mode, read the relevant blueprint sections, and present a plan. Wait for explicit human approval before writing code.
2. **Phase gates.** A phase is done only when its acceptance checklist in `PROMPTS-claude-code.md` passes, `make test` is green, and the phase's demo journey runs end-to-end via `make demo`.
3. **After every phase:** (a) run the `architecture-guardian` subagent on the diff and fix violations; (b) append an ADR entry to `docs/DECISIONS.md` for each significant choice; (c) give the human a **teach-back**: ≤15 lines explaining what was built and why, plus 3 quiz questions the human should be able to answer in an interview. Do not skip the teach-back.
4. When resuming a session, re-read this file and `docs/DECISIONS.md`, then state current phase status against its acceptance criteria before doing anything.

## Never build (cut list)

Real payment rails or real email delivery (drafts are real; "send" writes to DB + console). Multi-tenancy. Mobile. Real OCR (synthetic FNOLs carry text + ground truth). Fine-tuning. AWS deployment (the AWS profile is README documentation only). SIU/W3 tooling beyond the hand-off packet.

## Environment variables (human provides; never invent values)

`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` (session pooler), `LANGSMITH_API_KEY` (optional), `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

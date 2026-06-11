# Architecture Decision Records — Adjuster Zero

Append-only. Newest entries at the bottom of each phase. Never rewrite history.
Format: ADR-NNN, date, context, decision, consequences.

---

## Phase 0 — Foundations

### ADR-000 — Stack selection (zero-cost, AI-Lead-signal)
- **Date:** 2026-06-12
- **Context:** Need a deployable, ~€0/month stack that demonstrates production
  agent patterns and the tools AI-Lead interviews probe. The blueprint Part 5
  AWS design is the documented "production profile"; the live deployment must
  survive months unattended on free tiers.
- **Decision:** Agent = Python 3.12 + FastAPI + LangGraph (`PostgresSaver`) on
  Cloud Run (scale-to-zero). Web = Next.js 15 + Tailwind + shadcn on Vercel
  Hobby. Data/Auth/Realtime/Storage = Supabase (Postgres + pgvector + pg_cron).
  LLM = Gemini via `google-genai` (flash-lite default, flash for plan/tiebreak/
  letters). CI/cron = GitHub Actions. Tracing = LangSmith (env-gated).
- **Consequences:** `interrupt()` + PostgresSaver is the durable-HITL analogue of
  Step Functions `waitForTaskToken` (documented mapping is an interview asset).
  Free-tier RPM/RPD limits become a *feature* (admission control). All external
  dependencies are mocked; data is 100% synthetic.

### ADR-001 — The LLM proposes, the orchestrator disposes
- **Date:** 2026-06-12
- **Context:** Core thesis. The scarce skill is drawing the probabilistic/
  deterministic line and enforcing it structurally.
- **Decision:** Every LLM output is Pydantic-validated data, never a side effect.
  Routing is a pure function over typed inputs reading thresholds from `config`.
  No framework "auto" tool-calling loops for T1/T2 actions. Risk tiers are
  structural: `payment_execute` will *require* an `approval_ref`/`policy_gate_ref`
  as a constructor field (Phase 1), making an ungated call unrepresentable.
- **Consequences:** A single `GeminiClient` funnel enforces tiering, rate limits,
  RPD counters, and the structured-output contract repo-wide.

### ADR-002 — Structured output with exactly one repair retry
- **Date:** 2026-06-12
- **Context:** Hallucination-risk proxy #1 is schema-violation rate; silent retry
  loops are how demos become cost incidents.
- **Decision:** `GeminiClient.generate_structured` validates the model's JSON
  against the schema; on `ValidationError` it feeds the validator errors back for
  exactly ONE repair attempt, then raises `SchemaRepairFailed` (an
  `EscalateToHuman` subclass). Never a third attempt.
- **Consequences:** Tested in `tests/test_llm_repair.py` (no third call asserted).
  The bound is explicit, not emergent.

### ADR-003 — Token-bucket rate limiter per model, injectable clock
- **Date:** 2026-06-12
- **Context:** Free-tier RPM ceilings (flash 10, flash-lite 15). We must never
  self-inflict a 429, and the limiter must be unit-testable.
- **Decision:** A `TokenBucket` per model with an injectable `clock` so tests run
  without sleeping. Provider-side 429s are still handled in the client (backoff →
  flash→flash-lite downgrade → visible timeline event).
- **Consequences:** `make test` covers the limiter (Phase 0 acceptance).

### ADR-004 — Postgres connection model & checkpointer
- **Date:** 2026-06-12
- **Context:** LangGraph `PostgresSaver` uses prepared statements; Supabase
  poolers differ.
- **Decision:** Use the Supabase **session pooler** (port 5432) for
  `DATABASE_URL`. The agent service connects with the **service-role** key and
  bypasses RLS (trusted writer); the browser uses the anon key under RLS
  (public read, operator write). DB pool is optional at boot so the container
  serves `/healthz` before Supabase is wired.
- **Consequences:** Migrations are applied by the human (never by the agent);
  `db/README.md` has the exact steps.

### ADR-005 — Phase 0 guardian outcome
- **Date:** 2026-06-12
- **Context:** Ran the `architecture-guardian` on the Phase 0 skeleton.
- **Decision/Outcome:** Verdict **PASS WITH WARNINGS**, no blockers. Theses 3
  (one-repair-then-escalate) and 9 (single GeminiClient funnel + tiering) are
  implemented and tested; theses 1/2/4/5/6/7/8 are correctly WARN
  "not-yet-implemented" (business logic lands Phase 1+). Cosmetic fixes applied:
  simplified `downgrade()` and annotated the unreachable type-guard raise in
  `client._invoke`.
- **Consequences:** Re-audit thesis 1/7 (T2 structural gating, payment
  idempotency) when tools land in Phase 1.

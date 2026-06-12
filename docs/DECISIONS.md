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

---

## Phase 1 — Vertical slice (Journey A)

### ADR-006 — Lifecycle as a LangGraph StateGraph; deps in closures
- **Date:** 2026-06-12
- **Context:** The graph must be durably checkpointed yet hold non-serializable
  deps (store, planner, executor).
- **Decision:** State schema = the `ClaimAggregate` (serializable → checkpointed
  by PostgresSaver). Deps live in closures captured by `build_lifecycle_graph`,
  never in checkpointed state. Node order: intake → extract → classify →
  investigate → route → {w1_execute | park} → settle → close. Read-only (T0)
  investigation runs pre-routing with `workflow=None` (executor permits T0 only).
- **Consequences:** Fully testable in-memory with a fake planner + MemorySaver;
  prod uses AsyncPostgresSaver. Tests prove Journey A → CLOSED, lapsed → W2 park,
  missing → W4, budget exhaustion → ESCALATED.

### ADR-007 — Structural payment gate (thesis 4 made concrete)
- **Date:** 2026-06-12
- **Decision:** `PaymentAuthorization` (frozen) requires `policy_gate_ref` OR
  `approval_ref` via a model_validator; `PaymentExecuteArgs.authorization` is a
  required field with no default. An ungated payment is therefore unrepresentable
  at construction. Independently, the workflow allow-list places `payment_execute`
  only in W1, and the executor rejects it elsewhere (and permits only T0 during
  triage). Two independent guarantees that payment is unreachable off W1.
- **Consequences:** Tested at the validation level and the allow-list level.

### ADR-008 — Router reads versioned config; decisions record rule_id + version
- **Date:** 2026-06-12
- **Decision:** Phase 1 implements R-01/R-02/R-03/R-99 as a pure function over a
  `RoutingConfig` loaded from the active `config` row; every routing decision
  persists `rule_id` and `config_version` for reproducibility. Defaults are a
  fallback only (no DB / no row).
- **Consequences:** Policy changes are replayable against history (Phase 2 adds
  the remaining rules + hot-reload + R-06 LLM tiebreak).

### ADR-009 — Phase 1 guardian outcome + fixes
- **Date:** 2026-06-12
- **Outcome:** Verdict **PASS WITH WARNINGS**, no blockers. Fixes applied this
  phase from the guardian's findings:
  1. **Thesis 5 atomicity** — added `ClaimStore.commit_transition(agg, event)`
     wrapping the projection upsert and the event insert in ONE Postgres
     transaction; all lifecycle transitions now use it (no diverging state/event
     on a crash). Mid-EXECUTING financial accrual is not a transition and keeps a
     plain upsert.
  2. **Thesis 7 ambiguous failure** — the executor now catches non-`ToolFailure`
     handler exceptions (e.g. timeouts) and returns a NON-retryable failure
     (never propagates → no blind retry). Failed attempts record with a null
     idempotency key so they don't poison the unique slot or be mistaken for a
     settled payment. Tested.
  3. **Tool events** — clarified that tool activity is a first-class `tool_calls`
     entity merged into the timeline and streamed via Realtime (no duplicate
     `claim_events` row); corrected the executor docstring.
- **Deferred (tracked):** full rail reconcile-before-retry → Phase 4; sanctions
  fail-closed gate, fraud scan, citations/confidence-floor, full R-00..R-99,
  approvals/HITL → their respective phases (2/3). Replan counter exists but is
  unexercised until the Phase 2 replan edge.

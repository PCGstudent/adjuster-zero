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

---

## Phase 2 — Full routing + human-in-the-loop (Journeys B & D)

### ADR-010 — Full router R-00..R-99; R-06 tiebreak deferred
- **Date:** 2026-06-12
- **Decision:** Implemented all rules R-00..R-99 in the pure function. R-06
  (ambiguous fraud band 0.30–0.70) returns the conservative W2 default and sets
  `needs_tiebreak=True`; the LLM-with-RAG tiebreak that may override within the
  band is Phase 3 (keeps the router pure now). Exhaustive table-driven tests
  cover every rule, precedence, and config-driven thresholds.

### ADR-011 — HITL via interrupt() + checkpointer (= waitForTaskToken)
- **Date:** 2026-06-12
- **Context:** Durable human approval at zero compute cost while paused.
- **Decision:** W2 splits into `w2_propose` (create approval + draft denial
  letter / set reserve — runs once on the forward pass) and `w2_await` (calls
  `interrupt()` FIRST, so resume re-runs only this node and never double-fires
  the propose side effects). The resolve endpoint resumes with
  `Command(resume={resolution, delta, ...})`. W4 mirrors this for the document
  loop. This is the LangGraph analogue of Step Functions `waitForTaskToken`;
  state lives in the Postgres checkpointer, so a paused claim survives an
  agent-service restart — proven by `test_restart_survival_resumes_paused_claim`
  (fresh deps/executor, same checkpointer → resumes).
- **Consequences:** interrupt requires a checkpointer; the API always supplies
  one (PostgresSaver with a DB, a shared MemorySaver locally).

### ADR-012 — Payment gate widened to W2 (approval_ref), still structural
- **Date:** 2026-06-12
- **Decision:** `payment_execute` is now allow-listed in W1 (tier-0
  `policy_gate_ref`) AND W2, but the W2 path only constructs
  `PaymentAuthorization(approval_ref=appr_id)` AFTER `resolve_approval` returns —
  i.e. after a human signs. W3/W4/W5 have no payment edge (allow-list + graph
  topology). The structural guarantee (ungated payment unrepresentable) is
  unchanged; the W2 ref is a human approval rather than a policy gate.

### ADR-013 — Modify captures a structured delta + reason code
- **Date:** 2026-06-12
- **Decision:** On Modify, the inbox sends `delta` (e.g. `{"amount": 2000}`) +
  `reason_code`; the settlement uses the operator's amount, and the delta/reason
  persist on the approval row — the override data that feeds the Phase 4
  calibration chart. Proven by `test_w2_pay_modify_uses_my_amount`.

### ADR-014 — pg_cron timers write events
- **Date:** 2026-06-12
- **Decision:** `002_timers.sql` schedules a 72h document-reminder job and a 15-
  minute approval-SLA job; each INSERTs a `claim_events` row (event-sourced), so
  reminders/breaches appear on the live timeline like any other transition.

### ADR-015 — Phase 2 guardian outcome + fixes
- **Date:** 2026-06-12
- **Outcome:** Verdict **PASS WITH WARNINGS**, no blockers. Fixes applied:
  folded the W1 mid-EXECUTING financial accrual into the `settle` commit (no
  projection write without an event, thesis 5); added a `_check_budget` after the
  W2 denial-letter token accrual (thesis 6 symmetry). Deferred per scope:
  citation-coverage confidence floor (Phase 3), full rail reconcile-before-retry
  and sanctions fail-closed gate (Phase 4/later).

---

## Phase 3 — Grounding, fraud, and the glass cockpit (Journey C)

### ADR-016 — RAG as a grounding service; embedder abstraction with offline fallback
- **Date:** 2026-06-12
- **Decision:** 12 synthetic guideline docs → section-aware chunks → embeddings →
  hybrid retrieval (keyword + cosine, reciprocal-rank fusion). An `Embedder`
  protocol has `GeminiEmbedder` (prod, via GeminiClient → rate-limited/RPD) and a
  deterministic `LocalHashEmbedder` (stable md5 buckets) so retrieval + semantic-
  duplicate detection run offline/in tests without a key. Runtime uses an
  in-memory index without a DB and `PgGuidelineIndex` (populated by `make ingest`)
  with Supabase. 003_guidelines.sql adds the `vector(768)` store.

### ADR-017 — Grounded coverage + citation floor (thesis 8 enforced)
- **Date:** 2026-06-12
- **Decision:** `determine_coverage` (flash) decides coverage grounded only in
  retrieved chunks; the schema requires `citations`. `apply_citation_floor`
  validates citations against the retrieved chunk ids and floors confidence to
  0.5 when a determinative claim is uncited. Floored confidence (< 0.60) makes STP
  impossible and triggers R-05 → W5 human review (e2e tested). Offline attaches
  the top retrieved chunk as a citation chip to rules-only coverage.

### ADR-018 — Fraud path: semantic duplicates, weather, degraded mode
- **Date:** 2026-06-12
- **Decision:** `duplicate_claim_check` v2 adds narrative-embedding semantic
  matching (cosine ≥ 0.82) — paraphrases match even across perils. A degraded
  fraud control caps routing at W2 + emits `control.degraded_mode` (fail-closed,
  no STP). The `fraud_suspect` scenario scores 0.75 → W3, no payment edge.

### ADR-019 — R-06 tiebreak is the only LLM routing influence
- **Date:** 2026-06-12
- **Decision:** `route()` stays pure (conservative W2 + `needs_tiebreak`); the
  graph's `route_node` runs `decide_tiebreak` (flash + guidelines) for the
  ambiguous band only, restricted to W2/W3, persisted with alternatives.

### ADR-020 — Observability: own decision log + env-gated LangSmith
- **Date:** 2026-06-12
- **Decision:** `agent_decisions` + `claim_events` (trace_id minted at intake)
  are the primary trace; `obs.configure_tracing()` enables LangSmith only when
  configured. Cockpit renders the decision log (citations chips, alternatives,
  tokens, latency), a "chose NOT to" panel, a state-machine rail, and a global
  Agent Console.

### ADR-021 — Phase 3 guardian outcome
- **Date:** 2026-06-12
- **Outcome:** **PASS WITH WARNINGS**, no blockers. Added the thesis-8 e2e test
  (uncited determination → W5). Deferred to Phase 4: sanctions fail-closed
  pre-payment gate (T-11); a runtime (not toggle-only) degraded path.

---

## Phase 4 — Trust layer + showroom

### ADR-022 — Sanctions fail-closed + payment compensation (saga)
- **Date:** 2026-06-12
- **Decision:** `sanctions_watchlist_check` is a mandatory pre-payment screen
  (called in W1/W2 before `payment_execute`). When the sanctions service is
  unavailable (`sanctions_unavailable`), the executor blocks ALL `payment_execute`
  calls globally (fail-closed) — better a stuck claim than an unscreened payout.
  A blocked/failed payment triggers compensation: the reserve is restored and the
  claim returns to REVIEW_PENDING (a conditional `after_w1` edge routes the
  compensated branch away from settle). Tested in `test_hardening.py`.

### ADR-023 — Eval harness as a gate
- **Date:** 2026-06-12
- **Decision:** 50 labeled golden claims (`evals/golden/claims.json`) span all
  five routes. `run_evals` replays them through the REAL graph (offline-
  deterministic by default; real flash-lite when keyed, behind an RPD-budget
  guard), produces a route confusion matrix + pass rate, writes a report to
  `evals/reports/`, and records an `eval_runs` row. Wired to `make evals`, the
  weekly Action, and the Admin "Run evals" button. Current offline accuracy:
  route 100%, terminal 100% over 50 claims (gate is ≥92%).

### ADR-024 — Analytics from the event-sourced store
- **Date:** 2026-06-12
- **Decision:** KPIs (STP rate, override rate, cost/claim, schema-violation rate),
  the funnel, the confidence-calibration buckets (predicted vs. human agreement,
  fed by approval resolutions), the RPD meter, and the per-tool failure table are
  all derived from claims/approvals/tool_calls/decisions/llm_usage — no separate
  metrics pipeline (the event log IS the substrate).

### ADR-025 — Contact form is itself an agent
- **Date:** 2026-06-12
- **Decision:** The "Talk to me" form runs a minimal deterministic intake
  (qualify → one clarifying question if vague → create lead → draft an email to
  the owner) and surfaces its decisions + draft, with a `leads` table. Same
  thesis at small scale: the model proposes the draft; we dispose (store + would-
  email). No real email is sent (cut list).

### ADR-026 — Showroom layer
- **Date:** 2026-06-12
- **Decision:** Public landing (`/`) with the pitch, the three demo scenarios,
  "same engine, your process" translation cards, an honest tech summary, and a
  live nine-capabilities panel (event-type→capability map in one config file).
  Guided tour injects the three journeys sequentially with concept-naming
  narration. Viewer mode is public read-only via Supabase RLS (anon key);
  operator actions require auth.

### ADR-027 — Phase 4 guardian outcome (full-repo)
- **Date:** 2026-06-12
- **Outcome:** Full-repository audit, verdict **PASS WITH WARNINGS**, no blockers;
  all load-bearing theses (1/4/7) hold repo-wide (no unauthorized-payment path;
  no secrets committed; all data synthetic). Fixes applied: the R-06 tiebreak and
  the grounded coverage determination now accrue tokens to the per-claim budget
  and call `_check_budget` (thesis 6 completeness); `inject_scenario` and
  `run_claim` now commit the RECEIVED transition event-backed (no momentary
  projection-without-event; thesis 5).

### ADR-028 — Live bring-up (real Supabase + Gemini)
- **Date:** 2026-06-12
- **Outcome:** Applied migrations 001–004 (via `adjuster_zero.scripts.apply_migrations`,
  using the service-role DATABASE_URL), ingested the guideline corpus to pgvector
  (`make ingest`, 36 chunks), and validated all three journeys end-to-end against
  the real backend: A (clean_glass → W1 → CLOSED, RAG-cited), B (lapsed →
  REVIEW_PENDING → approve → DENIED, gated letter sent), C (fraud_suspect → W3,
  payments=0). Observability confirmed: model tiering in `llm_usage` (flash vs
  flash-lite vs embeddings), analytics KPIs, event stream.
- **Fixes surfaced only against Postgres** (the in-memory tests couldn't catch):
  approval id must be a UUID (now UUID5); `resolved_by` is a UUID FK (left NULL);
  embeddings pinned to 768 dims; Windows needs an explicit SelectorEventLoop for
  uvicorn. The remaining work — Cloud Run / Vercel / GitHub deploy — needs the
  human's cloud logins (`docs/deploy.md`).

### ADR-029 — Live flow page + coverage-grounding fix
- **Date:** 2026-06-12
- **Decision:** Added `/flow` — an editable FNOL + Go that animates the claim
  across the lifecycle diagram (pipeline → router → W1..W5 → terminal), nodes/
  edges lighting up from claim_events, backed by `POST /api/claims/inject_custom`
  (arbitrary text through the real graph). It makes the central thesis visible.
- **Bug found while building it (real, not flakiness):** the grounded
  `determine_coverage` saw only guideline chunks + the question, NOT the policy's
  carried coverages — so for a clean glass claim it hedged to covered=false /
  conf 0.20, hit the citation floor, and routed W5. Fix: pass the rules pre-screen
  (status, coverages carried, exclusions) into the determination so flash confirms
  and cites the governing chunk. Verified live: glass FNOL → W1 → CLOSED, coverage
  conf 1.00, cites G-AUTO-GLASS. The floor still fires for genuinely uncited cases.

### ADR-030 — WOW layer: vision · explainability · simulator · storm
- **Date:** 2026-06-12
- **Decision:** Four capability showcases, all live and on-thesis:
  - **Multimodal intake** — `describe_damage` (Gemini flash-lite vision) turns a
    photo into an FNOL that flows through the same deterministic pipeline.
    GeminiClient gained `images` support; `/api/claims/inject_vision`.
  - **Explainability agent** — `/api/claims/{id}/explain`: an agent reads the
    claim's OWN audit trail (events, decisions, citations) and explains the
    outcome in plain language (LLM live, deterministic fallback offline). Safe,
    read-only. The "can I trust it / why?" answer.
  - **Policy simulator** — `run_simulation` replays the 50-claim golden set under
    custom thresholds with no persistence → STP rate + workflow mix + confusion.
    `/api/admin/simulate` + `/simulate` sliders. Makes "routing is a pure,
    replayable function" interactive (raise the ceiling, watch STP move).
  - **Storm mode** — `/api/claims/storm` + `/api/stats`: inject 25 at once and
    watch the per-model token-bucket admission control queue them (in-flight badge).
- **Verified live:** vision sees an image; explain grounds in the trace; simulate
  default W1=12→ceiling-$10k W1=20 (STP 24%→40%); storm shows in-flight=5.

### ADR-031 — Deterministic intake completeness + date/location on intake
- **Date:** 2026-06-13
- **Problem:** A photo (and any terse FNOL) carries the damage but not *when* or
  *where* the loss happened, so every photo intake — and well-formed text claims —
  routed to W4 (information request). Two root causes: (1) the live-flow/vision
  intake had no way to supply loss_date / loss_location; (2) `completeness` that
  gates R-01 was the LLM's *self-reported* `overall_completeness`, which scored a
  fully-specified glass claim at 0.80 (< the 0.90 floor) → W4. The LLM was both
  proposing AND disposing on a routing input — a thesis-1/2 violation hiding in
  plain sight.
- **Decision:**
  1. **Completeness is now a deterministic projection** of the required intake
     facts — `policy_number, loss_date, loss_location` — computed by the
     orchestrator in `assess_completeness` (planner/extract.py), not taken from the
     LLM. `peril` is the classifier's job and `description` is the narrative itself,
     so neither gates completeness. `missing_required` is derived from the same
     check, so the W4 request asks for exactly the absent facts. The raw LLM
     self-score is still persisted in the decision record for observability.
  2. **Intake endpoints accept `loss_date` + `loss_location`** (`inject_custom`,
     `inject_vision`); `_compose_fnol` stitches them (and the policy number) into
     the FNOL, idempotently (no duplication when the text already names them). The
     extract node also folds a form-supplied policy number into the fields so
     completeness reflects what we actually know, not only what the LLM re-read.
  3. **Live-flow UI** gained a date picker + location field, pre-filled per preset.
- **Why this set of three:** they are the intake facts an adjuster cannot proceed
  without (who is covered, when, where); a missing one is precisely what you'd ask
  the claimant for. With 3 fields the 0.90 floor cleanly means "all three present."
- **Test fixtures:** four stubs that asserted W1/W2/W3/W5 routing carried no
  `loss_location` and only passed on the fake LLM `1.0`; they represent *complete*
  claims, so each gained a location. Added `tests/test_completeness.py` (5 tests)
  pinning the new contract. The W4-resume test now arrives genuinely incomplete
  (missing policy + date) rather than forcing `missing_required`.
- **Verified:** `make test` 81 green; golden-set replay route_accuracy **1.0** (50
  cases, unchanged mix); live — same FNOL without date/location → completeness 0.40
  → W4, *with* date+location → completeness 1.0 → routes onward.

### ADR-032 — Step-by-step walkthrough ("watch it think")
- **Date:** 2026-06-13
- **Decision:** A guided, manually-paced replay of a claim's life. New endpoint
  `GET /api/claims/{id}/journey` returns an ordered list of steps; each carries the
  step's real **input**, its **output**, and a plain-language explanation of what
  happened and why. New page `/walkthrough`: pick a scenario → it runs end-to-end →
  step through with Prev/Next (+ keyboard arrows + auto-play), a phase rail that
  lights the current lane, and an input→output→explanation card per step.
- **Why replay, not live-pause:** pausing the real graph at every node would mean
  interrupting the engine ~12× per claim — heavy, and it changes the lifecycle for a
  pedagogical view. Instead the claim runs normally and we project the
  already-persisted trace (decisions + tool calls + events). The builder
  (`api/journey.py`) is a **pure function**: no LLM, no side effects, deterministic
  given the trace. This is the event-sourcing thesis paying off — the audit log is
  rich enough to reconstruct the whole story after the fact.
- **Faithfulness (guardian-driven):** explanations are templated but **grounded in
  the recorded values**, not asserted. The coverage step says "floored to 0.5 and
  sent to a human" only when the recorded confidence actually was floored; the
  payment step quotes the real `policy_gate_ref`/`approval_ref` from the call's args;
  the narrative step shows the real FNOL as its input. The extract step explicitly
  contrasts the LLM's self-score ("ignored for routing") with the deterministic
  completeness (the authority) — the orchestrator-disposes thesis, made visible.
- **Determinism:** timeline merges decisions + tool calls by ISO `ts`, tie-broken by
  the executor's monotonic `seq`; stable sort ⇒ identical output for an identical
  trace.
- **Known follow-up (pre-existing, out of scope):** `tools/executor.py::_redact` is a
  no-op whose docstring promises redaction. Harmless today (synthetic data only), but
  the walkthrough is now a second consumer of raw tool args — implement or drop it
  before any real-looking refs/PII enter args.
- **Verified:** `make test` 82 green incl. `test_journey.py` (asserts pure projection,
  contiguous steps, RouterInput as the route step's input, deterministic completeness
  surfaced, payment gate present); web build clean.

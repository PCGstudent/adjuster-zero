# PROMPTS — Claude Code build kit for Adjuster Zero

> **Como usar (PT):** Cola um prompt de cada vez, pela ordem. Cada fase começa em *plan mode* (Shift+Tab) e o prompt já contém a palavra `ultrathink` para o turno de planeamento. Aprova o plano antes de deixar escrever código. No fim de cada fase, exige o relatório do `architecture-guardian`, o teach-back e as 3 perguntas de quiz — e responde-lhes tu, em voz alta. Se não souberes responder, pede explicação antes de avançar: o objetivo é ires a entrevistas a saber defender cada decisão. Modelos: planeamento/revisão em Opus 4.8 (`/model`), implementação em Sonnet 4.6; se só tiveres Sonnet, mantém e confia no ultrathink + plan mode.

---

## PHASE 0 — Foundations (repo, schema, hello-graph, pipelines)

ultrathink — Enter plan mode. Read CLAUDE.md fully, then docs/blueprint.md (skim all parts; read Part 6 SQL carefully) and docs/zero-cost-plan.md (sections 2–3). Confirm both docs exist in /docs; if not, stop and ask me to add them. Then present a plan for Phase 0 and wait for my approval.

**Goal:** a deployable skeleton where every pipeline works end-to-end before any product code exists.

**Scope (in):**
1. Monorepo per CLAUDE.md layout. `/agent`: uv project, FastAPI app with `/healthz`, Dockerfile (Cloud Run-ready, port from `$PORT`). `/web`: Next.js 15 + TypeScript + Tailwind + shadcn/ui, one page rendering "Adjuster Zero" and Supabase connection status. Makefile targets: `dev`, `test`, `lint`, `seed`, `demo`, `evals`.
2. `/db/migrations/001_init.sql`: the relational schema from blueprint Part 6 (users, sessions, claims, claim_events, conversations, workflow_executions, tool_calls, agent_decisions, approvals, audit_log) plus `config` (routing thresholds, versioned) and `documents`. Enable pgvector and pg_cron. Add RLS: `operator` full access, `viewer` read-only. Write `/db/README.md` with the exact `psql`/Supabase SQL editor steps for me to apply it; do not attempt to apply it yourself without my confirmation.
3. Hello-graph: a 2-node LangGraph (`ping → pong`) with `PostgresSaver` checkpointing to Supabase, exposed at `POST /debug/hello-graph`, proving checkpoint write/read round-trip.
4. `GeminiClient` wrapper skeleton in `/agent/src/llm/`: model tiering map, token-bucket rate limiter, persisted RPD counters (table `llm_usage`), structured-output helper with one-repair-retry, 429 backoff + downgrade. One `POST /debug/llm-echo` endpoint that classifies a toy sentence into a 3-field Pydantic schema to prove the pipeline.
5. CI: `.github/workflows/ci.yml` (ruff, mypy, pytest, web lint/build), `keepalive.yml` (daily: trivial Supabase query + Cloud Run ping), `evals.yml` placeholder (weekly cron, no-op for now).
6. `.env.example` complete; `docs/DECISIONS.md` created with ADR-000 (stack) entries.

**Scope (out):** any business logic, any UI beyond the status page, deployment execution (give me the exact `gcloud run deploy` and Vercel steps in `docs/deploy.md`; I run them).

**Acceptance:** `make dev` runs both apps locally; `/debug/hello-graph` shows a checkpoint persisted in Supabase (tell me the SQL to verify); `/debug/llm-echo` returns validated JSON and increments `llm_usage`; CI green on first push; `make test` includes at least rate-limiter unit tests.

**Close-out (mandatory):** run architecture-guardian on the repo; append ADRs; teach-back ≤15 lines + 3 quiz questions for me.

---

## PHASE 1 — Vertical slice: Journey A (the 90-second auto-settled claim)

ultrathink — Enter plan mode. Re-read CLAUDE.md theses 1–6 and blueprint Part 2 (W1, state machine), Part 3 (claim aggregate, executor), Part 4 (tools T-01..T-04, T-09, T-12, T-13, T-14). Present plan; wait for approval.

**Goal:** one claim, injected by a button, flows RECEIVED → TRIAGE → PLANNING → EXECUTING → SETTLEMENT → CLOSED fully autonomously, with every step live on the dashboard.

**Scope (in):**
1. **Synthetic data generator** (`make seed`): policies, claimants, and three parameterized FNOL scenarios — `clean_glass`, `lapsed_policy`, `missing_docs` — each with ground-truth labels stored for later evals. Build this FIRST.
2. **Claim aggregate** (Pydantic): state, extracted fields + per-field confidence, completeness, classification, fraud placeholder, financials, open questions. Persisted as projection of `claim_events`.
3. **LangGraph state machine** for the lifecycle with nodes `intake → extract → classify → route → w1_execute → settle → close`, PostgresSaver checkpointing, every node transition emitting a typed `claim_events` row (event envelope per blueprint Part 3).
4. **Planner v0:** `extract_fnol_fields` and `claim_classifier` as Gemini structured-output calls through GeminiClient (flash-lite), schema-validated, one repair retry, decisions persisted to `agent_decisions` with confidence + alternatives + tokens + latency.
5. **Router v0:** pure function with rules R-01, R-02, R-03, R-99 only (others return W2 default), thresholds from `config`, full unit tests, decision persisted with `rule_id`.
6. **Tool layer v0:** registry (name → Pydantic in/out schemas, risk_tier, idempotent flag, handler); executor validates args against schema before invoke and result after; uniform `{ok, data|error}` envelope. Implement mocks: `policy_lookup`, `coverage_check` (rules-only stub, no RAG yet), `repair_cost_estimator`, `reserve_set` (idempotency key), `payment_execute` (T2: constructor REQUIRES `policy_gate_ref`; idempotency key; reconcile-before-retry stub), `customer_comm_send` (draft mode only).
7. **Dashboard v1:** Claims queue (state badge, workflow chip, confidence) + Claim detail with the live Execution Timeline fed by Supabase Realtime on `claim_events` (expandable tool calls with args/result JSON). Plain-language labels per CLAUDE.md conventions. "Inject clean claim" button (operator role).
8. Per-claim token budget + replan counter scaffolding in the executor (enforced, even if replans don't exist yet).

**Scope (out):** W2–W5, approvals/HITL, RAG, fraud, analytics, showroom.

**Acceptance:** from a fresh `make seed`, clicking "Inject clean claim" produces a CLOSED claim in under ~2 minutes with ≥6 tool calls visible live; the lapsed-policy scenario routes to W2 default and parks (no payment path reachable — prove with a test); `pytest` covers router rules, schema-validation repair path, payment idempotency, and that `payment_execute` cannot be constructed without a gate ref (compile/validation-level test); timeline updates without page refresh.

**Close-out:** guardian run; ADRs; teach-back + 3 quiz questions (one must be: "why does the LLM never own control flow?").

---

## PHASE 2 — Real routing + human-in-the-loop: Journeys B and D

ultrathink — Enter plan mode. Re-read blueprint Part 2 (full rule table, escalation paths, W2/W4/W5), Part 3 (approval layer), Part 4 (T-05 rules-only, T-07, T-15, T-18), and zero-cost-plan section 2 (interrupt/resume mapping). Present plan; wait for approval.

**Scope (in):**
1. **Full router R-00..R-99** as pure function + exhaustive unit tests (table-driven); hot-reload from versioned `config`; `config_version` recorded on every routing decision.
2. **Risk tiers enforced structurally** across the registry (T0/T1/T2 per blueprint); workflow allow-lists: executor rejects any plan step whose tool is not allowed for the routed workflow.
3. **Workflows W2 and W4** (+ W5 as escalate-with-packet stub): W2 runs investigation then pauses at the approval gate via LangGraph `interrupt()`; W4 issues `document_request_create`, parks in INFO_PENDING, resumes on document arrival (simulated upload endpoint).
4. **Approval layer:** `approvals` rows with requested_action, evidence refs, confidence, SLA; **Approval Inbox UI** with Approve / Modify / Reject; Modify captures a structured delta + reason code; resolve endpoint resumes the graph with `Command(resume=...)`. A claim must survive an agent-service restart while paused (checkpointer proof).
5. **Timers:** pg_cron jobs for 72h document reminders and approval SLA flags, each writing events.
6. New tools: `fraud_signal_scan` (rules-only v1), `claim_history`, `duplicate_claim_check` (exact match), `document_request_create`, `escalate_to_human`. Fast-deny path (R-02) drafts the denial letter (flash) and routes to REVIEW_PENDING.
7. Inject buttons for `lapsed_policy` and `missing_docs` scenarios.

**Acceptance:** Journey B: lapsed policy → covered=false with the lapse reason → drafted denial → REVIEW_PENDING → I approve in the inbox → DENIED with letter and full audit trail. Journey D: a W2 claim proposes a payout; I Modify the amount; delta + reason persisted; settlement uses my amount. Kill and restart the agent service while a claim is paused → approval still resumes correctly. Tests: every routing rule; allow-list rejection; interrupt/resume round-trip; no payment without approval_ref on W2 (structural test).

**Close-out:** guardian; ADRs; teach-back + 3 quiz questions (one must be: "explain interrupt()+checkpointer vs Step Functions waitForTaskToken").

---

## PHASE 3 — Grounding, fraud, and the full glass cockpit: Journey C

ultrathink — Enter plan mode. Re-read blueprint Part 3 (RAG layer, memory), Part 4 (T-03 real, T-05 hybrid, T-06 semantic, T-10, T-17), Part 7 (decision log, hallucination proxies). Present plan; wait for approval.

**Scope (in):**
1. **Guideline corpus:** write ~12 short, realistic underwriting-guideline documents (auto glass/collision/hail, property, exclusions, lapse rules) as markdown in `/db/guidelines/`; ingestion script: section-aware chunking → `gemini-embedding-001` → pgvector; hybrid retrieval (Postgres full-text + kNN, simple rank fusion) as `guideline_search`.
2. **`coverage_check` v2:** Gemini (flash) determination grounded in retrieved chunks; output schema requires citations; a validator computes citation coverage and floors confidence < 0.5 when uncited → forces human review (thesis 8). Citations render in the timeline as chips linking to the guideline text.
3. **Fraud path:** `duplicate_claim_check` v2 (narrative embeddings, cosine threshold), `weather_event_verify` (mock NOAA dataset), `fraud_signal_scan` v2 (rules + flash-lite assist) returning score + itemized signals with evidence; degraded-mode rule (any control down ⇒ cap at W2, emit DEGRADED_MODE event). R-06 tiebreak: flash with retrieved guidelines, persisted with alternatives.
4. **Decision log as UI:** every `agent_decisions` row rendered in the cockpit — confidence, alternatives with probabilities, citations, tokens, latency — plus the **"chose NOT to" panel**: tools the planner skipped with its one-line reasons.
5. **Agent Console** page: global live event stream across all claims (Realtime).
6. **State-machine graph** in the claim detail right rail with traversed path highlighted (use the real state list; a simple SVG/flow render is fine).
7. LangSmith tracing wired (env-gated) around graph runs and LLM calls; `trace_id` propagated into events.
8. Inject button for the `fraud_suspect` scenario (extend the generator: 3 prior claims, near-duplicate narrative, recent coverage increase).

**Acceptance:** Journey C: fraud scenario → score > 0.70 with ≥3 itemized signals and evidence → routed W3 → hand-off packet visible → prove via test that no payment edge is reachable from W3. A clean claim shows ≥1 citation chip on coverage; an artificially uncited determination gets confidence-floored and parks for review (test). Duplicate detection demonstrably semantic (paraphrased narrative still matches). Console streams events from two concurrent claims.

**Close-out:** guardian; ADRs; teach-back + 3 quiz questions (one must be: "name our hallucination-risk proxies and where each is enforced").

---

## PHASE 4 — Trust layer + showroom (evals, calibration, guided tour, landing)

ultrathink — Enter plan mode. Re-read blueprint Parts 7–10, zero-cost-plan sections 4–6, and the showroom layer description below. Present plan; wait for approval.

**Scope (in):**
1. **Eval harness:** `/evals/golden/` with 50 labeled synthetic claims (route + expected terminal state + key fields); runner replays them through the real graph (flash-lite), produces route confusion matrix + pass rate, writes a report to `/evals/reports/` and a row to an `eval_runs` table; wired to weekly GitHub Action AND an admin "Run evals" button (with RPD-budget guard: refuse if insufficient quota remains).
2. **Analytics page:** KPI tiles (STP rate, median cycle time, override rate, cost/claim, schema-violation rate), funnel, **confidence-calibration chart** (predicted confidence vs human agreement by bucket, fed by approval resolutions), RPD budget meter, per-tool failure table.
3. **Hardening:** payment reconcile-before-retry completed; compensation path (failed settlement → reserve restored → REVIEW_PENDING) with test; token/replan budget exhaustion test; config versioning surfaced in UI.
4. **Showroom layer:**
   - **Landing page** (public, `/`): headline "Watch an AI agent run a complete business process — live, right now." Sections: 60-second pitch; the three demo scenarios as cards; "Same engine, your process" translation cards (claims ↔ invoices ↔ inbound leads ↔ support tickets); honest tech summary (stack, €0/month, all-synthetic data); CTA "Want this on your process? Talk to me" linking to the contact agent. Tasteful, fast, shadcn-based; no stock-photo aesthetic.
   - **Guided tour mode:** a "Watch the guided demo" button runs the three scenarios sequentially with step-synced narration callouts that NAME the concepts as they happen ("this is workflow routing — rule R-03 fired", "this pause is human-in-the-loop via a durable interrupt"). Narration script: write it from blueprint Part 2 journeys A/B/C; keep each callout ≤ 2 sentences; I will review the copy before you wire it.
   - **Nine-capabilities panel:** receives objective → understands intent → chooses workflow → selects tools → executes → maintains state → handles uncertainty → escalates to a human → produces measurable outcomes. Each item lights up in real time as the corresponding event type arrives for the running claim. Event-type→capability mapping in one config file.
   - **Viewer mode:** public read-only access via RLS `viewer` role (no login wall for reading; operator actions require login). "Reset demo data" admin button.
   - **Contact-form easter egg:** the site's "Talk to me" form is itself handled by a minimal intake graph (qualify → one clarifying question if vague → create lead row → email-draft to me as event) with its own tiny timeline view and a caption: "Yes — this contact form is also an agent. Inspect its decisions here."
5. **README + docs:** final README in English with the one-paragraph pitch (blueprint appendix), architecture diagram, the AWS↔zero-cost mapping table (from zero-cost-plan §1), "What the LLM is NOT allowed to do" section, cost report placeholder, and `docs/demo-script.md` (the 7-minute interview script from zero-cost-plan §5).

**Acceptance:** `make evals` produces a report with ≥92% route accuracy on the golden set (iterate on prompts/rules until true — changes gated by the eval run); calibration chart renders with ≥40 human-resolved approvals (I will adjudicate seeds; build me a fast adjudication queue UI for this); guided tour runs unattended through all three scenarios without errors at free-tier rate limits (queueing visible, never crashing); landing Lighthouse ≥90 performance; viewer link works logged-out; contact agent round-trips.

**Close-out:** guardian full-repo run; ADRs; final teach-back covering the WHOLE system in ≤30 lines + a 10-question interview self-test for me.

---

## UTILITY PROMPTS

**Resume a session:**
> Re-read CLAUDE.md and docs/DECISIONS.md. State which phase we are in and the status of each acceptance criterion for that phase (met / not met / unverified), then propose the next single step. Do not write code yet.

**Phase-end deep audit (optional, only on a model with xhigh):**
> /effort ultracode — then: Audit the entire repository against the 10 checks in .claude/agents/architecture-guardian.md. Cover every directory including tests, seeds, scripts, and workflows. Produce the guardian's report format. Make no edits.

**When it drifts or over-builds:**
> Stop. Re-read CLAUDE.md "Never build" and the current phase's Scope (out). List anything you've added that exceeds scope, propose what to delete or defer, and wait for my decision.

**Teach me (use freely):**
> Explain {file or concept} to me as if preparing me for a CTO interview: what it does, why this design over the obvious alternative, what breaks if we remove it, and one question an interviewer would ask about it.

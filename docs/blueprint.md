# Adjuster Zero — A Portfolio-Grade Autonomous Claims Operations Agent

**A complete product, architecture, and build blueprint for a production-pattern AI agent system a solo engineer can MVP in four weekends.**

---

## Executive Summary

The project: **Adjuster Zero**, an autonomous insurance claims operations platform. It receives a First Notice of Loss (FNOL), extracts and validates the claim, classifies it, **routes it to one of five distinct workflows**, executes investigation and settlement steps through a typed tool layer, sets financial reserves, pays small clean claims straight-through with zero human touch, and escalates everything ambiguous, expensive, or suspicious to a human approval queue — while rendering every plan, decision, confidence score, and tool call on a transparent "glass cockpit" dashboard.

The opinionated architectural stance that makes this a portfolio signal rather than a demo: **the LLM never owns control flow.** The LLM proposes (plans, classifications, drafts); a deterministic state machine disposes (routes, gates, executes, compensates). Money never moves without either a hard-coded policy tier or a human signature. Every decision is replayable from an append-only event log. That stance — knowing exactly what to delegate to a probabilistic component and what to keep deterministic — is the single thing that separates AI Leads from prompt engineers, and this project makes the stance visible on screen.

---

# PART 1 — IDEA SELECTION

## The 10 Candidates

### 1. Autonomous Insurance Claims Triage & Adjudication ("Adjuster Zero")
**Problem.** Insurers spend $40–70 per claim on manual handling; 60–70% of low-severity claims are routine enough for straight-through processing (STP), yet most carriers auto-settle under 25% because triage, coverage verification, fraud screening, and payment authorization live in disconnected systems and humans glue them together.
**Why it demonstrates agent expertise.** Claims is the canonical business-process-automation domain: rich multi-way routing (STP vs. standard adjudication vs. fraud investigation vs. information-request loops vs. high-severity escalation), document extraction, RAG over underwriting guidelines, money-moving tools that demand hard human gates, fraud scoring that demands uncertainty handling, and KPIs (STP rate, cycle time, leakage) that a CEO understands in one sentence.
**Technical difficulty.** High — but bounded. Every external dependency (valuation APIs, weather data, payments, sanctions lists) mocks cleanly with synthetic data, so the orchestration complexity is real while the integration burden is fake-able.
**Portfolio impact.** Very high. Nobody builds this; everybody builds support chatbots.
**Hiring manager impact.** Very high. The demo narrative ("watch the agent settle this claim in 90 seconds, then watch it refuse to settle this one and explain why") sells itself.
**Business realism.** Very high. Lemonade, Tractable, and every P&C carrier's innovation team are spending real money on exactly this.

### 2. DevOps Incident Response Agent
**Problem.** On-call engineers burn hours triaging alerts, correlating signals, and executing runbooks at 3 a.m.
**Why agentic.** Diagnosis → hypothesis → tool-driven investigation → remediation proposal → human approval for destructive actions. Genuine multi-step reasoning under uncertainty.
**Difficulty.** High. **Portfolio impact.** High with technical audiences. **Hiring manager impact.** High for infra-heavy companies, lower elsewhere. **Business realism.** High.
**Fatal weakness.** Demos terribly without real infrastructure. Simulated outages on simulated clusters read as a toy; real outages can't be staged on demand in an interview. The "actions" (restart pod, roll back deploy) are either dangerous or obviously fake.

### 3. Accounts Payable Invoice-to-Payment Agent
**Problem.** AP teams manually key invoices, perform 3-way matching (invoice ↔ PO ↔ goods receipt), chase approvals, and post to the ledger.
**Why agentic.** Extraction, matching with fuzzy tolerance, exception routing, approval chains, payment execution.
**Difficulty.** Medium. **Portfolio.** High. **Hiring manager.** High. **Realism.** Very high (Ramp, Bill.com territory).
**Weakness.** The happy path is nearly linear — extract → match → approve → pay. Routing is mostly exception handling, so the multi-workflow story is thinner than claims.

### 4. E-commerce Returns & RMA Resolution Agent
**Problem.** Returns processing mixes policy lookup, fraud detection (wardrobing, serial returners), label generation, refund vs. replacement vs. store-credit decisions.
**Why agentic.** Visible branching, real side effects, fraud-driven uncertainty.
**Difficulty.** Medium. **Portfolio.** Medium-high. **Hiring manager.** Medium-high. **Realism.** High.
**Weakness.** Lower stakes per decision; reads as a Shopify app rather than an enterprise system.

### 5. Accounts Receivable Collections & Dunning Negotiation Agent
**Problem.** SMBs write off billions in late receivables because chasing invoices is awkward, manual, and unprioritized.
**Why agentic.** Strategy selection per debtor, multi-step negotiation within policy bounds (payment plans, discounts), measurable in literal dollars collected.
**Difficulty.** Medium. **Portfolio.** High. **Hiring manager.** High. **Realism.** Very high.
**Weakness.** The core "action" is sending persuasive emails — to a skeptical reviewer it pattern-matches to spam automation, and autonomous outbound communication is precisely the capability hiring managers are most nervous about.

### 6. KYC / Compliance Onboarding Agent
**Problem.** Fintechs hand-review identity documents, screen against sanctions/PEP lists, and risk-score applicants.
**Why agentic.** Document verification, watchlist tooling, risk-tiered routing, regulator-grade audit trails.
**Difficulty.** Medium-high. **Portfolio.** High. **Hiring manager.** High in fintech. **Realism.** Very high.
**Weakness.** The decision space is narrow (approve / review / reject); workflow diversity is limited, and the most impressive parts (real document forensics) can't be faked credibly.

### 7. SOC Security Alert Triage Agent
**Problem.** Security analysts drown in alerts; 90%+ are benign.
**Why agentic.** Enrichment tooling (IOC lookups, geo, asset context), hypothesis-driven investigation, escalate/close decisions, incident write-ups.
**Difficulty.** High. **Portfolio.** High for security-adjacent roles. **Hiring manager.** Niche. **Realism.** High.
**Weakness.** Same demo problem as #2 — credible alerts require credible telemetry, and the audience that appreciates it is narrow.

### 8. Contract Review & Redlining Agent
**Problem.** Legal teams bottleneck on NDA/MSA review against internal playbooks.
**Why agentic.** RAG over playbooks, clause classification, redline proposal, risk-tiered escalation to counsel.
**Difficulty.** Medium. **Portfolio.** Medium. **Hiring manager.** Medium. **Realism.** High but crowded (a dozen funded startups).
**Weakness.** It's fundamentally one workflow (review → redline → escalate). Heavy on RAG, light on orchestration — drifts back toward the "RAG app" category this project must escape.

### 9. Multi-System Customer Support Resolution Agent
**Problem.** Support agents toggle between CRM, billing, shipping, and KB to resolve tickets.
**Why agentic.** Intent classification, workflow selection (refund vs. troubleshoot vs. account change), tool execution across systems.
**Difficulty.** Medium. **Portfolio.** Low-medium. **Hiring manager.** Low-medium. **Realism.** Very high.
**Fatal weakness.** It is the default portfolio project of 2024–2026. However well executed, a reviewer's prior is "another support bot," and you spend the interview fighting that prior instead of demonstrating depth.

### 10. Recruiting Screening & Scheduling Agent
**Problem.** Recruiters spend hours screening résumés and coordinating interviews.
**Why agentic.** Parsing, scoring, scheduling tools, outreach drafting.
**Difficulty.** Low-medium. **Portfolio.** Low. **Hiring manager.** Actively risky — automated candidate screening triggers immediate bias/EEOC concerns; you'd be demoing a liability. **Realism.** High commercially, toxic reputationally.

## Scoring Matrix (1–5)

| # | Idea | Technical difficulty | Portfolio impact | Hiring-manager impact | Business realism | Demo-ability w/ synthetic data | Workflow-routing richness |
|---|------|---|---|---|---|---|---|
| 1 | Claims triage (Adjuster Zero) | 4 | 5 | 5 | 5 | **5** | **5** |
| 2 | Incident response | 5 | 4 | 4 | 4 | 2 | 4 |
| 3 | AP invoice-to-pay | 3 | 4 | 4 | 5 | 4 | 3 |
| 5 | AR collections | 3 | 4 | 4 | 5 | 4 | 3 |
| 6 | KYC onboarding | 4 | 4 | 4 | 5 | 3 | 2 |
| 7 | SOC triage | 4 | 4 | 3 | 4 | 2 | 3 |
| 4 | Returns/RMA | 3 | 3 | 3 | 4 | 4 | 4 |
| 8 | Contract redlining | 3 | 3 | 3 | 4 | 4 | 2 |
| 9 | Support resolution | 3 | 2 | 2 | 5 | 4 | 3 |
| 10 | Recruiting screener | 2 | 1 | 1 | 4 | 4 | 2 |

## Ranking, Strongest → Weakest

**1. Claims triage** · 2. Incident response · 3. AP invoice-to-pay · 4. AR collections · 5. KYC onboarding · 6. SOC triage · 7. Returns/RMA · 8. Contract redlining · 9. Support resolution · 10. Recruiting screener.

## The Winner: Adjuster Zero — and Why It Beats the Field

**It maximizes the one variable this portfolio exists to demonstrate: visible orchestration.** Five genuinely distinct workflows with different tools, different risk gates, and different terminal states. AP, KYC, and contract review are each essentially one workflow with exception branches; claims is a true router.

**It is fully demo-able with synthetic data — and that is decisive.** Incident response and SOC triage are arguably "cooler" but cannot be staged convincingly. A synthetic FNOL with a synthetic policy, a mocked NOAA weather record, and a mocked valuation API is indistinguishable from the real thing in a demo, because the *system behavior* is the product. You control the entire demo narrative: feed it a clean $1,800 windshield claim and watch it settle in 90 seconds; feed it the same claim with a policy that lapsed yesterday and watch it refuse; feed it a claimant with three prior claims this year and watch it route to fraud investigation with cited evidence.

**Human-in-the-loop is native to the domain, not bolted on.** In a support bot, escalation feels like a failure mode. In claims, the approval gate on a $14,000 payout is *the entire point* — regulators require it. The project gets to showcase HITL as a designed product surface (an approval inbox with evidence, confidence, and alternatives) rather than an apology.

**The stakes force real engineering.** A chatbot that hallucinates wastes a user's time. An agent that hallucinates moves money. That single fact justifies — and lets you show off — idempotency keys, saga compensation, risk-tiered tool gating, audit logs, confidence calibration, and replay. None of the weaker ideas *require* that machinery; here it's load-bearing.

**The KPIs speak CEO.** "Straight-through-processing rate went from 0% to 38% on the synthetic book, median cycle time 4 minutes, zero unauthorized payments, 6% human-override rate on agent proposals." No other idea on the list produces a sentence that good.

**It is unfashionable, which is the point.** Insurance reads as boring, and boring is the moat: a reviewer has seen forty RAG chatbots this quarter and zero claims-adjudication state machines. Differentiation is free.

---

# PART 2 — PRODUCT DESIGN

## Product Vision

**Adjuster Zero is the zeroth adjuster that touches every claim.** It resolves the routine majority autonomously, prepares the complex minority so thoroughly that human adjusters start at 80% done, and proves every decision with an audit trail a regulator could read. The product's signature is **radical transparency**: the dashboard is a glass cockpit where users watch the agent think — its classification, its chosen workflow, its plan, every tool call with arguments and results, every confidence score, and every moment it decided it was *not* confident enough and asked a human.

**Positioning sentence:** "An autonomous claims department with a paper trail."

## User Personas

**1. Claims Operations Manager ("Dana") — primary.** Owns STP rate and cycle time. Lives in the Approval Inbox and Analytics screens. Needs to trust the agent enough to raise the auto-pay ceiling from $1,000 to $2,500 — and needs the calibration data to defend that decision to her boss.

**2. Senior Adjuster ("Marcus").** Receives escalated claims. Needs the agent's investigation packet (extracted facts, tool evidence, guideline citations, fraud signals) presented so he starts from analysis, not from a blank file. His "modify" actions are the system's most valuable training signal.

**3. SIU Fraud Investigator ("Priya").** Receives fraud-flagged claims with the signal breakdown. Agent assists (runs lookups on request) but never decides; in fraud workflows the human leads and the agent is a tool-wielding analyst.

**4. Platform Admin / Auditor ("Theo").** Manages tool registry, risk-tier thresholds, guideline corpus, and pulls audit exports. The persona that exists to prove the system is governable.

**5. (Demo persona) The Reviewer.** The hiring manager watching the screen. Every UI decision is secretly optimized for this persona: the system must be legible to a smart outsider in under three minutes.

## Core Workflows

| ID | Workflow | Trigger | Terminal states | Human touch |
|----|----------|---------|----------------|-------------|
| W1 | **Straight-Through Processing** | Low severity, full coverage, fraud score < 0.30, amount ≤ auto-pay ceiling, confidence ≥ 0.85 | SETTLED (auto-paid) | Zero |
| W2 | **Standard Adjudication** | Medium severity/amount, clean fraud screen | SETTLED or DENIED after human approval | Approve/modify/reject proposal |
| W3 | **Fraud Investigation (SIU)** | Fraud score > 0.70 OR specific hard signals (duplicate claim, watchlist hit) | Referred; agent becomes assistant | Human-led |
| W4 | **Information Request Loop** | Completeness < 0.90 or low-confidence extraction | Returns to triage on receipt; WITHDRAWN on timeout | Zero (claimant-facing) |
| W5 | **High-Severity Escalation** | Severity ≥ 4, injury flag, amount > $25k, coverage ambiguity, legal-rep flag | Assigned to senior adjuster with prepared packet | Human-led, agent prepares |

## User Journeys

**Journey A — the 90-second settle (W1).** Claimant submits FNOL: cracked windshield, photo, policy #. Agent extracts fields (conf 0.96) → verifies policy active, glass coverage with $0 deductible (cites guideline G-AUTO-114) → fraud screen 0.08 → repair estimate $412 from parts table → all gates green → tier-0 payment executes → settlement email drafted and sent → claim CLOSED. Dashboard shows 9 steps, 6 tool calls, total cost $0.04 in tokens, elapsed 87s. **This is the demo opener.**

**Journey B — the refusal.** Same claim, but policy lapsed 6 days before loss date. `coverage_check` returns covered=false citing the lapse clause. Agent routes to *fast-deny* path → drafts denial letter with citation → because denial is consequential, risk tier forces REVIEW_PENDING. Dana sees the proposal, the policy timeline, and the cited clause; approves in one click. **This is the demo's trust moment: the agent declining to act is more impressive than acting.**

**Journey C — the fraud catch.** Claimant's third claim in 11 months; `duplicate_claim_check` finds near-identical loss description from 4 months ago (cosine 0.93); loss reported 2 days after a coverage increase. Fraud score 0.81. Agent halts adjudication, compiles a signal report, routes W3, notifies Priya. No payment path is reachable from this state — provably, in the state machine.

**Journey D — the approver's day.** Dana opens the Approval Inbox: 7 pending. Each card shows requested action ("Pay $3,840 to claimant via ACH"), evidence summary, confidence 0.88, fraud 0.21, the agent's rationale with guideline citations, and a cheaper alternative the agent considered. She approves 5, modifies 1 (reduces payout — depreciation the agent missed; her correction is logged as override data), rejects 1 back to W5.

**Journey E — the patient loop (W4).** Missing police report → agent sends document request with portal link → claim parks in INFO_PENDING → EventBridge Scheduler fires a 72h reminder → doc arrives → re-triage → W2.

## Screens

**S1 — Claims Queue.** Table of claims: state badge, workflow chip, severity, amount, fraud score, confidence, SLA countdown, owner (AGENT / human name). Filters by state and workflow. This screen alone communicates "this is an operations system, not a chat app."

**S2 — Claim Detail: the Glass Cockpit (the money screen).**
- *Left rail:* claim facts (extracted fields with per-field confidence), documents, claimant comms thread, financials (reserve, paid, remaining limit).
- *Center:* the **Execution Timeline** — an expandable vertical trace: classification (with alternatives + scores), routing decision (rule that fired), plan (steps with status), each tool call (collapsible args/result JSON, latency, retries), each decision record, each approval. Live-updating via WebSocket/polling while the claim runs.
- *Right rail:* the state machine rendered as a graph with the current state highlighted and the traversed path drawn — the single most screenshot-able element in the product.

**S3 — Approval Inbox.** Card stack of pending approvals sorted by SLA risk. Each card: requested action, evidence, confidence, fraud score, citations, alternatives, [Approve] [Modify] [Reject → escalate].

**S4 — Agent Console.** Live event stream across all claims (the "mission control" wall): `claim.triage.completed`, `tool.completed`, `approval.requested`… Pure observability theater, high demo value, trivial to build off the event bus.

**S5 — Analytics.** KPI tiles (STP rate, median cycle time, override rate, cost/claim, token spend), funnel chart (received → triaged → auto vs. human → settled), **confidence-calibration chart** (predicted confidence vs. human-agreement rate by bucket), tool failure-rate table.

**S6 — Admin.** Tool registry (name, schema, risk tier, enabled), routing thresholds (hot-editable config), guideline corpus manager (upload → chunk → embed), audit export.

## Dashboard Layout (S2 wireframe)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ CLM-2026-00417  Auto/Glass  ●EXECUTING   W1 STP   conf 0.91  fraud 0.08  │
├────────────────┬──────────────────────────────────────┬──────────────────┤
│ CLAIM FACTS    │ EXECUTION TIMELINE                   │ STATE MACHINE    │
│ policy POL-88..│ ✔ 10:02:11 Intake validated          │   RECEIVED       │
│ holder J. Ortiz│ ✔ 10:02:14 Classified: auto/glass    │      ↓           │
│ loss 2026-06-08│     sev 1  alt: auto/collision 0.06  │   TRIAGE ✔       │
│ amount ~$412   │ ✔ 10:02:14 Routed → W1 (rule R-03)   │      ↓           │
│ fields 8/8 ✔   │ ✔ 10:02:21 ⚙ policy_lookup     211ms │   PLANNING ✔     │
│────────────────│ ✔ 10:02:23 ⚙ coverage_check    1.4s  │      ↓           │
│ DOCUMENTS      │     covered ✔ cites [G-AUTO-114]     │ ▶ EXECUTING      │
│ photo_1.jpg ✔  │ ✔ 10:02:25 ⚙ fraud_signal_scan 0.08  │      ↓           │
│────────────────│ ▶ 10:02:26 ⚙ repair_cost_estimator…  │   SETTLEMENT     │
│ FINANCIALS     │ ○ payment_execute (tier-0, queued)   │      ↓           │
│ reserve $450   │ ○ customer_comm_send                 │   CLOSED         │
└────────────────┴──────────────────────────────────────┴──────────────────┘
```

## Agent Architecture (product-level view)

One **agent**, many **workflows**. The agent is the planning/reasoning capability; workflows are typed, inspectable execution programs the agent's router selects and the orchestrator runs. (Full component architecture in Part 3.)

## Decision Engine — How the AI Chooses Among Workflows

**Opinionated rule: routing is a policy decision, not a vibe.** The LLM produces *typed inputs* to routing (classification, severity, completeness, extraction confidence). Routing itself is a deterministic rule table over those inputs plus business facts (amount, fraud score, policy flags). The LLM breaks ties only when the table is ambiguous — and every tie-break is logged as a decision record with alternatives and rationale. This gives you the holy trinity: explainability ("rule R-03 fired"), hot-tunability (thresholds live in config, no redeploy), and testability (the router is a pure function with a unit-test suite).

**Routing rule table (evaluated top-down, first match wins):**

| Rule | Condition | Route |
|------|-----------|-------|
| R-00 | watchlist hit OR duplicate-claim hard match | W3 Fraud |
| R-01 | completeness < 0.90 OR any required field conf < 0.80 | W4 Info Request |
| R-02 | policy inactive at loss date OR clear exclusion (conf ≥ 0.90) | Fast-deny → W2 review |
| R-03 | fraud < 0.30 AND severity ≤ 2 AND est. amount ≤ ceiling AND coverage conf ≥ 0.85 | **W1 STP** |
| R-04 | fraud > 0.70 | W3 Fraud |
| R-05 | severity ≥ 4 OR injury OR amount > $25k OR attorney flag OR coverage conf < 0.60 | W5 High-Severity |
| R-06 | 0.30 ≤ fraud ≤ 0.70 → LLM tie-break with guideline RAG; logged | W2 or W3 |
| R-99 | default | W2 Standard |

## Decision Tree

```
                              FNOL received
                                   │
                       completeness ≥ 0.90 ? ──no──► W4 INFO REQUEST ──docs──┐
                                   │ yes                 (72h reminder,      │
                                   ▼                      30d auto-close)    │
                       policy active & covered ?                             │
                          │no              │yes        re-enter triage ◄─────┘
                          ▼                ▼
                 FAST DENY (draft      fraud score ?
                 letter, cite clause,      │
                 human confirms)  ┌────────┼──────────────┐
                               <0.30   0.30–0.70        >0.70
                                  │        │               │
                                  ▼        ▼               ▼
                            severity &   LLM tie-break   W3 FRAUD / SIU
                            amount ?     (RAG-grounded,  (human-led; no
                          ┌─────┴────┐    logged)        payment reachable)
                  sev≤2 & ≤$2,500   else      │
                  conf ≥ 0.85         │   ┌───┴───┐
                          │           ▼   ▼       ▼
                          ▼      W2 STANDARD     W3
                     W1 STP      (HITL approve
                  (auto-pay,      pay/deny)
                   zero touch)
```

## State Machine

```
            ┌──────────┐
   FNOL ───►│ RECEIVED │
            └────┬─────┘
                 ▼
            ┌──────────┐   incomplete      ┌──────────────┐
            │  TRIAGE  ├──────────────────►│ INFO_PENDING │◄── reminder t+72h
            └────┬─────┘                   └──────┬───────┘    (EventBridge
                 │ routed                  docs   │  timeout    Scheduler)
                 ▼                         in ▼   ▼ 30d
            ┌──────────┐              (re-TRIAGE)  WITHDRAWN ◄ terminal
            │ PLANNING │
            └────┬─────┘ plan validated
                 ▼
            ┌───────────┐ tool fail ×3 / invariant ┌────────┐
            │ EXECUTING ├─────────────────────────►│ FAILED │─► COMPENSATING
            └────┬──────┘                          └────────┘   (reverse side
                 │ plan complete                                 effects, then
                 ▼                                               ESCALATED)
        ┌─ risk tier? ─┐
   tier-0│             │tier-1/2
        ▼              ▼
   SETTLEMENT   ┌────────────────┐ approve ┌────────────┐  paid  ┌────────┐
   (auto)──────►│ REVIEW_PENDING ├────────►│ SETTLEMENT ├───────►│ CLOSED │
                └──┬─────────┬───┘         └────────────┘        └────────┘
            reject│          │modify(Δ logged as override)
                  ▼          └────────► SETTLEMENT (modified)
              ESCALATED / DENIED  ◄ terminal (letter + audit)
```

**Guards** (enforced by the orchestrator, not the LLM): no transition into SETTLEMENT without `coverage.covered = true` AND (`tier = 0` OR approval record exists); no payment tool invocable outside SETTLEMENT; W3 states have no edge to SETTLEMENT at all.

## Workflow Orchestration

Each workflow is a declarative definition (Step Functions ASL in production; an in-process interpreter in Week 1): ordered phases, each phase a set of tool steps with retry policy, plus gate conditions between phases. The Planner may *propose* skipping or adding steps within a phase; the orchestrator validates proposals against the workflow's allowed-tool set and gate invariants before execution. Re-planning is permitted at phase boundaries only, max 2 re-plans per claim, then escalate — unbounded agent loops are how demos become incidents.

## Escalation Paths

| Trigger | Destination | What the human receives |
|---|---|---|
| Confidence below gate at any phase | REVIEW_PENDING | Proposal + evidence + alternatives |
| Fraud score > 0.70 / hard signal | W3 / SIU queue | Signal report with per-signal evidence |
| Tool failure after retries | ESCALATED (ops) | Failing step, error chain, claim snapshot |
| LLM output fails schema 2× | ESCALATED | Raw outputs + validator errors |
| Amount > human's own approval limit | Next approver tier | Same card, re-routed |
| SLA breach in REVIEW_PENDING | SNS page to Dana | Aging approval alert |
| Claimant disputes outcome | W5 senior adjuster | Full claim packet + dispute text |

---

# PART 3 — AGENT ARCHITECTURE

## Component Map

```
                                  ┌────────────────────────────────────────┐
                                  │            OBSERVABILITY LAYER          │
                                  │  traces · decision log · metrics · evals│
                                  └────────────▲───────────────▲────────────┘
                                               │ (every component emits)
┌──────────┐  FNOL/API   ┌─────────┐  typed    ┌─────────┐ workflow ┌────────────┐
│ Ingestion├────────────►│ PLANNER ├──────────►│ ROUTER  ├─────────►│  EXECUTOR  │
│  /Intake │  normalized │  (LLM)  │ class.,   │ (rules  │ selection│ (state     │
└──────────┘  ClaimAgg.  └────┬────┘ plan      │ + LLM   │          │  machine)  │
                              │      proposals │ tiebreak)│          └─────┬──────┘
                              │                └─────────┘                │ step
                              │ retrieves                                 ▼
                        ┌─────▼─────┐                              ┌────────────┐
                        │ RAG LAYER │◄────── guideline queries ────┤ TOOL LAYER │
                        │ (guidelines│                              │ registry · │
                        │  + history)│                              │ validation·│
                        └───────────┘                              │ idempotency│
                              ▲                                    └─────┬──────┘
                              │                                          │ results
                        ┌─────┴───────────────────────────────┐          │
                        │            MEMORY LAYER              │◄─────────┘
                        │ working (claim aggregate, DynamoDB)  │
                        │ episodic (append-only event log)     │
                        │ semantic (vector index)              │
                        │ tool cache (TTL)                     │
                        └─────────────────▲────────────────────┘
                                          │ pause/resume (task tokens)
                              ┌───────────┴────────────┐
                              │  HUMAN APPROVAL LAYER  │
                              │  inbox · SLA timers ·  │
                              │  override capture      │
                              └────────────────────────┘
```

## Component Responsibilities

**Ingestion / Intake.** Accepts FNOL via web form, email webhook, or API. Normalizes into a *Claim Aggregate* (the canonical working-memory object), stores raw documents in S3, assigns `claim_id` and `trace_id`, emits `claim.received`. Deliberately dumb: no LLM here, so garbage input fails loudly before it reaches the expensive layers.

**Planner (LLM).** The only component allowed to be creative. Three jobs: (1) **extraction** — documents → typed fields with per-field confidence; (2) **classification** — line/peril/severity/complexity with alternatives; (3) **planning** — given the routed workflow's template, propose the concrete step list with arguments. Every output is constrained to a JSON Schema and validated before anything downstream consumes it; on validation failure the validator errors are fed back for exactly one repair attempt, then escalate. The Planner has *no execution authority* — it returns data structures, never side effects.

**Router.** A pure, unit-tested function: `route(classification, completeness, fraud_score, amount, policy_flags, config) → {workflow, rule_id}`. Thresholds load from a hot-reloadable config record. Only rule R-06's ambiguous band invokes the LLM (with guideline RAG context), and that call is logged as a first-class decision with alternatives. Purity is the feature: you can replay every historical routing against a new rule table to test policy changes — that's how Dana safely raises the auto-pay ceiling.

**Executor (Orchestrator).** Owns the state machine. Takes the validated plan, walks workflow phases, dispatches tool steps, enforces gate invariants and risk tiers, manages retries/timeouts, pauses on approvals (task tokens), triggers compensation on failure. In production this is AWS Step Functions; in Week 1 it's a 200-line interpreter over the same JSON workflow definitions — same semantics, swappable later. **This component, not the LLM, is the agent's spine.**

**Tool Layer.** A registry mapping `tool_name → {json_schema_in, json_schema_out, risk_tier, handler, timeout, retry_policy, idempotent}`. Responsibilities: argument validation against schema *before* invocation; result validation after; idempotency-key enforcement for side-effecting tools; per-tool circuit breakers; uniform error envelope (`{ok, data | error: {code, message, retryable}}`). Risk tiers: **T0** read-only (free to call), **T1** reversible writes (allowed inside an approved plan), **T2** money/external comms (requires explicit human approval *per invocation* unless the W1 tier-0 policy gate covers it).

**Memory Layer.** Four stores, four jobs. *Working memory:* the Claim Aggregate in DynamoDB — current state, extracted facts, open questions, accumulated tool evidence; this is what gets serialized into every Planner prompt (no chat-history sludge — the aggregate is the context, deliberately curated and capped). *Episodic memory:* the append-only event log; the system of record from which the aggregate is a projection — enabling replay and audit. *Semantic memory:* vector index over guidelines and (stretch) embedded historical claims for "similar past claims" retrieval. *Tool cache:* content-hash keyed, TTL'd, so a re-plan doesn't re-bill a valuation API.

**RAG Layer.** Ingestion pipeline (S3 upload → section-aware chunking → embeddings → index) and a query API used by `coverage_check`, `guideline_search`, and the R-06 tie-break. Hybrid retrieval (BM25 + kNN, reciprocal-rank fusion). **Citation enforcement:** adjudication outputs must reference retrieved chunk IDs; the validator computes citation coverage and an uncited coverage determination is treated as a hallucination risk → confidence is floored → routes to human review. RAG here is a *grounding service for decisions*, not a chat feature.

**Human Approval Layer.** Approval task creation (with evidence packet, confidence, alternatives), inbox API, SLA timers via EventBridge Scheduler, and resolution capture. Critically, it records *deltas*: when Marcus modifies a payout from $3,840 → $3,310, the system stores the structured diff + reason code. Override data is the ground truth that feeds the calibration chart and, later, fine-tuning.

**Observability Layer.** Receives structured events from every component (single logging contract, Part 7), maintains the decision log, computes metrics, runs the nightly eval harness. Not a sidecar afterthought — components *cannot* perform a state transition without emitting the corresponding event, because the event *is* the transition (event-sourced).

## How Components Communicate

**Pattern: synchronous edges for humans, asynchronous events for the machine.** The dashboard/API path is request-response; everything between agent components flows through the event bus and queues, with all state living in the database — components share *data*, never in-memory objects.

```
1. Ingestion  ──► put ClaimAggregate ──► emit claim.received
2. Planner λ  ◄── triggered by claim.received
              ──► extraction + classification ──► emit claim.triage_ready
3. Router λ   ◄── claim.triage_ready
              ──► decision record (rule_id, alternatives) ──► emit claim.routed{W?}
4. Executor   ◄── claim.routed starts the workflow execution
   for each step:
              ──► SQS tool-queue ──► Tool worker λ ──► result to aggregate
              ──► emit tool.completed / tool.failed
   at gates:  ──► evaluate invariants; on T1/T2 ──► approval task + task-token pause
5. Approval   ◄── human acts in inbox ──► resolve token ──► emit approval.resolved
6. Executor   resumes ──► settlement / terminal ──► emit claim.closed
   (every emit ──► Observability projector ──► metrics, traces, console stream)
```

Event envelope (versioned, on the bus as `source=adjuster.zero`, `detail-type=claim.routed` etc.):

```json
{
  "event_id": "evt_01J...", "trace_id": "trc_...", "claim_id": "CLM-2026-00417",
  "type": "claim.routed", "v": 1, "ts": "2026-06-11T10:02:14Z",
  "actor": {"kind": "agent", "component": "router"},
  "data": {"workflow": "W1", "rule_id": "R-03", "inputs_hash": "sha256:..."}
}
```

Why this shape: components stay independently deployable and independently *fail-able*; a poisoned tool call lands in a DLQ instead of wedging the claim; and the event stream doubles as the audit log, the dashboard feed, and the replay substrate. Three features for the price of one design decision.

---

# PART 4 — TOOL CALLING

## Tool-Layer Contract

Every tool registers `{name, description, json_schema_in, json_schema_out, risk_tier, timeout_ms, retry: {max, backoff}, idempotent}`. The Planner selects tools dynamically by emitting plan steps that reference registry names; the Executor rejects any step whose tool is absent from the routed workflow's allow-list or whose arguments fail schema validation (one repair round-trip with the validator error, then escalate with reason `TOOL_ARG_INVALID`). All tools return the uniform envelope:

```json
{"ok": true, "data": { ... }}                                   // success
{"ok": false, "error": {"code": "POLICY_NOT_FOUND",
                        "message": "...", "retryable": false}}  // failure
```

Schemas below are abbreviated for readability; the registry stores full JSON Schema with types, enums, and required fields.

### T-01 `extract_fnol_fields` — T0, idempotent
**Purpose.** Turn raw FNOL text + documents into typed claim fields with per-field confidence.
**In.** `{claim_id, document_ids: [s3_key], hint_line?: "auto|property|injury"}`
**Out.** `{fields: {policy_number, loss_date, loss_location, peril, description, claimed_amount?, ...}, field_confidence: {policy_number: 0.99, ...}, missing_required: ["police_report"], overall_completeness: 0.84}`
**Example.** Photo + free-text "rock hit my windshield on I-80 yesterday" → `{peril: "glass", loss_date: "2026-06-08", overall_completeness: 0.92}`.
**Failure.** Unreadable document → `DOC_UNREADABLE` (not retryable) → router sends W4 with a "please re-upload" request. LLM JSON invalid → one schema-repair retry → escalate.

### T-02 `policy_lookup` — T0, idempotent
**Purpose.** Fetch policy record from the policy-admin system (mock).
**In.** `{policy_number}` **Out.** `{policy_id, status: "active|lapsed|cancelled", holder, effective_from, effective_to, coverages: [{code, limit, deductible}], endorsements: []}`
**Example.** `POL-88341` → active, AUTO-COMP limit 50000, glass deductible 0.
**Failure.** `POLICY_NOT_FOUND` → fuzzy search on holder name + DOB; single high-confidence match → proceed with `match_confidence` attached; else escalate `IDENTITY_UNRESOLVED`. Timeout → retry ×2 exponential → DLQ.

### T-03 `coverage_check` — T0
**Purpose.** Determine whether the loss is covered, grounded in the guideline corpus.
**In.** `{policy_id, peril, loss_date, jurisdiction, fields}`
**Out.** `{covered: bool, confidence, applicable_coverage: "AUTO-COMP", exclusions_triggered: [], citations: ["G-AUTO-114#c3"], rationale}`
**Example.** Glass loss, active comp coverage → `covered: true, conf 0.94, citations [G-AUTO-114#c3]`.
**Failure.** Citation coverage < 100% of determinative claims → confidence floored to 0.5 → cannot satisfy R-03 → human review. Retrieval returns nothing above score floor → `GUIDELINE_GAP` → W5.

### T-04 `claim_classifier` — T0, idempotent
**Purpose.** Line/peril/severity/complexity classification with alternatives.
**In.** `{fnol_text, fields}` **Out.** `{line, peril, severity: 1-5, complexity: "low|med|high", injury_flag, attorney_flag, confidence, alternatives: [{label, p}]}`
**Failure.** Top-2 margin < 0.15 → emit both as alternatives, set `confidence` to margin-adjusted value; router thresholds handle the rest. Never guess silently.

### T-05 `fraud_signal_scan` — T0
**Purpose.** Hybrid rules + LLM fraud screen producing a score *and* itemized evidence.
**In.** `{claim_id}` **Out.** `{score: 0.81, signals: [{code: "DUP_NARRATIVE", weight: 0.35, evidence: "cosine 0.93 vs CLM-2025-09112"}, {code: "RECENT_COVERAGE_INCREASE", weight: 0.20, evidence: "limit +40% 9d before loss"}]}`
**Failure.** Any sub-check erroring → that signal reported as `UNAVAILABLE` and **score is treated as a lower bound**; if unavailable signals could cross the 0.70 line, route conservative (W2 minimum, never W1). Fail toward suspicion, never toward auto-pay.

### T-06 `duplicate_claim_check` — T0, idempotent
**Purpose.** Exact (claimant/VIN/address + date-window) and semantic (narrative embedding) duplicate detection.
**In.** `{claim_id, claimant_id, vin?, narrative}` **Out.** `{exact_matches: [], semantic_matches: [{claim_id, similarity}]}`
**Failure.** Vector index down → degrade to exact-match only, emit `DEGRADED_MODE` event, cap routing at W2 (no STP while a fraud control is degraded — this rule impresses reviewers).

### T-07 `claim_history` — T0, idempotent
**Purpose.** Claimant's prior claims and loss ratio. **In.** `{claimant_id}` **Out.** `{prior_claims: [{claim_id, date, peril, paid}], count_24m, loss_ratio}`
**Failure.** Not found → return empty history with `first_seen: true` (a weak fraud signal itself, weighted in T-05).

### T-08 `vehicle_valuation` — T0, idempotent, cached 24h
**Purpose.** Actual cash value (mock KBB/NADA). **In.** `{vin? | make, model, year, mileage, condition, zip}` **Out.** `{acv: 14250, range: [13400, 15100], source: "mock-nada", as_of}`
**Failure.** VIN decode fails → fall back to make/model/year with `valuation_basis: "estimated"`, which caps risk tier at T1 for any payout (estimated values never auto-pay).

### T-09 `repair_cost_estimator` — T0
**Purpose.** Line-item estimate from a parts/labor table. **In.** `{line, damage_items: [{part, severity}], vehicle_meta | property_meta, zip}` **Out.** `{line_items: [{desc, parts, labor_hours, rate, total}], total: 412, confidence}`
**Failure.** Unknown part code → estimate remaining items, flag `PARTIAL_ESTIMATE`, total becomes a floor → blocks R-03's "amount ≤ ceiling" check from passing on incomplete data.

### T-10 `weather_event_verify` — T0, idempotent, cached
**Purpose.** Corroborate weather perils against an events dataset (mock NOAA). **In.** `{lat, lng, date, peril}` **Out.** `{verified: true, event: {type: "hail", magnitude: "1.75in", distance_km: 3.1}, source}`
**Example.** Hail claim, Des Moines, 2026-05-14 → verified, supports both coverage and fraud-negative signal.
**Failure.** `verified: false` is a *finding*, not an error — feeds T-05 as `PERIL_UNCORROBORATED (weight 0.25)`. API down → `UNAVAILABLE`, signal excluded, conservative routing per T-05 rule.

### T-11 `sanctions_watchlist_check` — T0, **mandatory pre-payment**
**Purpose.** Screen payee against OFAC-style list (mock). **In.** `{payee_name, dob?, country}` **Out.** `{hit: false, matches: []}`
**Failure.** Any hit (even fuzzy ≥ 0.85) → hard stop, R-00 → W3, payment edge unreachable. Service down → **payments globally blocked** (fail-closed); claims queue in REVIEW_PENDING with reason `COMPLIANCE_UNAVAILABLE`. This tool failing open would be the system's worst bug; saying so in the README is a maturity signal.

### T-12 `reserve_set` — **T1**, idempotent via key
**Purpose.** Set/adjust the financial reserve. **In.** `{claim_id, amount, rationale, idempotency_key}` **Out.** `{reserve_id, previous_amount, new_amount}`
**Failure.** Ledger write fails after retries → claim to FAILED → compensation is a no-op (reserve unchanged) → ESCALATED. Duplicate key → return prior result (exactly-once semantics).

### T-13 `payment_execute` — **T2**, idempotent via key
**Purpose.** Disburse settlement (mock ACH). **In.** `{claim_id, payee_id, amount, method, approval_ref | policy_gate_ref, idempotency_key}`
**Out.** `{payment_id, status: "settled", settled_at}`
**Example.** `{amount: 412, policy_gate_ref: "W1-T0-ceiling-2500", idempotency_key: "CLM-417-pay-1"}` → `pay_8812 settled`.
**Failure.** The crown jewel of failure design. Rejected (e.g., bad account) → not retryable → compensation: reserve restored, claim → REVIEW_PENDING with `PAYMENT_REJECTED`. Timeout (ambiguous!) → **never blind-retry a payment**: reconcile by idempotency key first; only retry if provably absent. Missing `approval_ref`/`gate_ref` → executor refuses the call before it leaves the process — the check is structural, not behavioral.

### T-14 `customer_comm_send` — **T2** (send) / T0 (draft)
**Purpose.** Draft and send claimant communications from templates. **In.** `{claim_id, template_id, merge_fields, channel: "email", mode: "draft|send"}` **Out.** `{message_id?, draft_id, rendered_preview}`
**Failure.** Template merge-field missing → draft fails loudly (`TEMPLATE_INCOMPLETE`) rather than sending a letter with blanks. Send bounce → retry alternate channel, log to comms thread, never blocks settlement.

### T-15 `document_request_create` — T1
**Purpose.** Request specific documents; opens the W4 loop. **In.** `{claim_id, doc_types: ["police_report"], due_days: 14}` **Out.** `{request_id, portal_url, expires_at}`
**Failure.** Notification failure → request still recorded; reminder scheduler retries delivery; claim correctly sits in INFO_PENDING either way (state is truth, notification is best-effort).

### T-16 `inspection_schedule` — T1
**Purpose.** Book a field inspection (mock calendar). **In.** `{claim_id, location, window_start, window_end}` **Out.** `{appointment_id, inspector, slot}`
**Failure.** No slots in window → return alternatives → Planner proposes new window once → else escalate to ops with `SCHEDULING_CONFLICT`.

### T-17 `guideline_search` — T0, idempotent
**Purpose.** RAG retrieval over the guideline corpus. **In.** `{query, line?, k: 5}` **Out.** `{chunks: [{id, doc, section, text, score}]}`
**Failure.** All scores below floor → empty result with `LOW_RELEVANCE` — consumers must treat as "no grounding," never as "no objection."

### T-18 `escalate_to_human` — T1, the universal exit
**Purpose.** Create a human task with full context. **In.** `{claim_id, reason_code, risk_tier, summary, requested_action?, evidence_refs: []}` **Out.** `{task_id, queue, sla_at}`
**Failure.** If even this fails → CloudWatch alarm → SNS page. The escape hatch gets its own escape hatch.

## Dynamic Tool Selection in Practice

For CLM-417 (W1 glass claim) the Planner proposed: `policy_lookup → coverage_check → fraud_signal_scan → duplicate_claim_check → repair_cost_estimator → reserve_set → [gate] → payment_execute → customer_comm_send`. It *omitted* `vehicle_valuation` (repair, not total loss), `weather_event_verify` (peril isn't weather), and `inspection_schedule` (photo evidence sufficient at this severity) — and the dashboard renders the omissions with the Planner's one-line reasons. **Showing what the agent chose *not* to do is the cheapest, highest-impact transparency feature in the entire system.** For a hail claim, the same Planner pulls in T-10; for a suspected total loss, T-08 replaces T-09. Selection is real, bounded by the workflow allow-list, and visible.

---

# PART 5 — AWS IMPLEMENTATION

## Architecture Diagram

```
                                ┌─────────────────────────── AWS ────────────────────────────────┐
  Browser (Dana/Marcus)         │                                                                 │
       │                        │   ┌────────────┐      ┌──────────────────────────┐             │
       ├──HTTPS──► CloudFront ──┼──►│ S3: static │      │ Cognito (user pool, JWT) │             │
       │          (CDN, TLS)    │   │ Next.js UI │      └────────────▲─────────────┘             │
       │                        │   └────────────┘                   │ authorizer                │
       └──HTTPS /api───────────►│  API Gateway (HTTP API) ───────────┘                           │
                                │        │                                                       │
                                │        ▼                                                       │
                                │  Lambda: api-handler (claims CRUD, inbox, analytics,           │
                                │  SendTaskSuccess on approval)                                   │
                                │        │                                                       │
                                │        ▼                                                       │
                                │  DynamoDB single-table  ──streams──►  Lambda: projector        │
                                │  (claims, events, decisions,          (metrics, console feed,  │
                                │   approvals, tool calls)               S3 archive)             │
                                │        │                                                       │
                                │        ▼  custom bus: adjuster.zero                            │
                                │  EventBridge ────────────────► EventBridge Scheduler           │
                                │   │        │                   (reminders, SLA timers)         │
                                │   │        └────────► SNS (ops alerts, approver email)         │
                                │   ▼                                                            │
                                │  Step Functions: ClaimLifecycle (Standard, task tokens)        │
                                │   │   per tool step                                            │
                                │   ▼                                                            │
                                │  SQS tool-queue ──► Lambda: tool-workers ──► DLQ + alarm       │
                                │                       │        │                               │
                                │                       │        ├─► Bedrock: Claude (planner/   │
                                │                       │        │   classifier), Titan embed    │
                                │                       │        ├─► OpenSearch (guideline RAG)  │
                                │                       │        ├─► S3 (documents, results)     │
                                │                       │        └─► Secrets Manager (keys)      │
                                │                       ▼                                        │
                                │            CloudWatch Logs/Metrics/Dashboards + X-Ray          │
                                └─────────────────────────────────────────────────────────────────┘
```

## Service Roles & Key Decisions

**Frontend.** Next.js static export on **S3 + CloudFront** (or Amplify Hosting if you want CI for free). No SSR server to babysit; the dashboard polls + uses lightweight SSE from API Gateway.

**API Gateway (HTTP API) + Lambda `api-handler`.** One FastAPI/Hono Lambda behind HTTP API (cheaper and simpler than REST API). Cognito JWT authorizer. Endpoints: FNOL intake, claim list/detail, timeline feed, approval inbox, approval resolve (calls `states:SendTaskSuccess`), admin config.

**Step Functions — the orchestrator, and the most important choice in the stack.** *Standard* workflow per claim: it natively gives you the state machine, retries with backoff, `waitForTaskToken` for human approvals (a claim can sit in REVIEW_PENDING for days at zero compute cost), execution history as a free audit artifact, and a console graph that mirrors your dashboard. Tool fan-out within a phase uses a Map state. Hot LLM loops (extract→validate→repair) run *inside* one Lambda invocation, not as SFN transitions — Standard transitions cost money and add latency; don't pay state-machine prices for a while-loop.

**DynamoDB.** Single-table, on-demand capacity (spiky agent traffic is exactly what on-demand is for). Streams feed the projector Lambda. Schema in Part 6.

**SQS.** Decouples Executor from tool workers; per-tool-group queues with DLQs (poison tool calls park for inspection instead of wedging claims). Long-running tools use the SFN "wait for callback" pattern over SQS.

**SNS.** Human-facing notifications: approver emails, SLA-breach pages, DLQ alarms.

**EventBridge.** Custom bus `adjuster.zero` carries every domain event (Part 3 envelope); rules fan out to the projector, the console stream, and SNS. **EventBridge Scheduler** owns time: 72h document reminders, 30d auto-close, approval SLA timers — one-shot schedules per claim, deleted on resolution.

**OpenSearch.** Guideline corpus: hybrid BM25 + kNN. Smallest viable domain (single `t3.small.search`) — or see the cheap profile below, because OpenSearch is the line item that eats hobby budgets.

**Bedrock.** Claude Haiku-class for extraction/classification (cheap, fast, structured), Sonnet-class for planning and the R-06 tie-break; Titan for embeddings. Keeping inference inside AWS keeps IAM as the only credential story. (Direct Anthropic API is a fine substitute; then Secrets Manager earns its keep.)

**CloudWatch + X-Ray.** Structured JSON logs with Embedded Metric Format (metrics ride the log line — no separate metric pipeline), Logs Insights for ad-hoc forensics, X-Ray tracing across API → SFN → tools. Dashboards in Part 7.

**Secrets Manager.** Third-party keys (Anthropic, mock-API tokens), rotated; Lambdas read at cold start and cache.

## Scaling Story

Everything stateful is managed; everything compute is stateless — so scaling is concurrency math, not architecture changes. Lambda scales per-claim horizontally (set reserved concurrency on tool workers to respect mock-API rate limits); SQS absorbs intake bursts (a 10,000-claim catastrophe event becomes a deep queue, not an outage — and *that sentence is the scaling story to tell in the interview*); DynamoDB on-demand rides the spike; Step Functions Standard runs ~1M open executions without tuning. The genuine bottlenecks, in order: (1) **LLM TPM quotas** — mitigate with queue-based admission control and per-claim token budgets; (2) OpenSearch query latency under fan-out — mitigate with the tool cache; (3) your wallet.

## Cost Optimization

The bill is LLM tokens first, OpenSearch second, everything else rounding error at portfolio volume. Levers, in order of leverage: **model tiering** (Haiku-class for extract/classify ≈ 80% of calls, Sonnet-class only for plans/tie-breaks — cuts token spend ~5–10×); **prompt caching** on the static prompt prefix (workflow definitions, tool registry excerpt, guideline preamble); **tool-result caching** (valuations, weather, policy lookups are content-addressable); **per-claim token budget** enforced by the Executor (a runaway re-plan loop is a cost incident — budget exhaustion → escalate, which is also correct behavior); aggregate-not-transcript prompting (the Claim Aggregate keeps context small by construction); DynamoDB on-demand + 30-day TTL on raw tool-result blobs (S3 keeps the archive). Track **cost-per-claim as a first-class KPI** on the analytics screen — a number CTOs never see from candidates, which is exactly why you show it.

## Free-Tier-Friendly Profile (the "weekend wallet" stack)

Note: AWS moved new accounts to a credits-based Free Plan in mid-2025, so "free tier" now mostly means "fits comfortably in the starter credits / costs single-digit dollars." Verify current terms before deploying.

| Production choice | Cheap swap | Why it's fine for the demo |
|---|---|---|
| OpenSearch domain | **pgvector on RDS/Aurora smallest instance**, or simpler: **FAISS/sqlite-vec index built offline, shipped in a Lambda layer** (guideline corpus is ~200 chunks, rebuild on upload) | Same hybrid-retrieval semantics; OpenSearch is the only painful line item |
| Bedrock Sonnet everywhere | Haiku-class default, Sonnet only for planning; aggressive prompt caching | Quality where it matters, pennies elsewhere |
| Cognito | Keep it (low MAU is effectively free) or a signed-cookie demo login | Auth isn't the point of the portfolio |
| X-Ray everywhere | CloudWatch EMF + your own trace_id propagation | You're building a decision-trace UI anyway — it *is* your tracing |
| Per-claim SFN Standard | Keep it — transitions at demo volume are pennies; the execution-history audit trail is worth more than the dollars | Don't optimize away your best artifact |
| NAT Gateway (the classic trap) | **No VPC for Lambdas at all** — nothing here needs one if you skip RDS/OpenSearch | NAT is ~$32/mo of pure regret on hobby projects |

Realistic demo-month bill on the cheap profile: **low single-digit dollars + LLM tokens (~$0.02–0.10/claim with tiering)**. Run 500 synthetic claims for the price of a coffee.

---

# PART 6 — DATABASE DESIGN

## Primary: DynamoDB Single-Table (`az_main`)

Event-sourced core: the `EVT#` items are the system of record; the claim aggregate is a projection; everything is replayable.

| Entity | PK | SK | Key attributes |
|---|---|---|---|
| User | `USER#<id>` | `PROFILE` | email, name, role (`ops_manager\|adjuster\|siu\|admin`), approval_limit, created_at |
| Session | `USER#<id>` | `SESSION#<iso_ts>` | jwt_id, ip, ua, expires_at (TTL) |
| Claim aggregate | `CLAIM#<id>` | `META` | state, workflow, line, peril, severity, fraud_score, confidence, completeness, amount_est, reserve, paid, claimant_id, policy_id, assignee, sla_at, version (optimistic lock), updated_at |
| Event (episodic log) | `CLAIM#<id>` | `EVT#<iso_ts>#<seq>` | type, v, actor{kind,component\|user_id}, data, trace_id |
| Conversation msg | `CLAIM#<id>` | `MSG#<iso_ts>` | direction (in/out), channel, author, body_ref(S3), template_id |
| Workflow execution | `CLAIM#<id>` | `WF#<exec_id>` | workflow, sfn_arn, status, started_at, ended_at, phase, replan_count, token_budget_used |
| Tool call | `WF#<exec_id>` | `TOOL#<seq>` | tool, risk_tier, args(S3 ref if >4KB), args_hash, idempotency_key, status, result_ref, error_code, latency_ms, retries, cached |
| Agent decision | `CLAIM#<id>` | `DEC#<iso_ts>#<seq>` | decision_type (`classify\|route\|plan\|tiebreak\|action`), model, prompt_hash, input_refs, output, confidence, alternatives[], citations[], guardrails{schema_ok, citation_coverage}, tokens{in,out}, latency_ms |
| Approval task | `APPR#<id>` | `META` | claim_id, requested_action, risk_tier, evidence_refs, confidence, status, sla_at, resolved_by, resolution (`approve\|modify\|reject`), delta (structured diff), reason_code |
| Audit log | `AUDIT#<yyyy-mm-dd>` | `<iso_ts>#<actor>#<seq>` | action, subject, before_hash, after_hash, ip — append-only; stream-archived to S3 (WORM-style) |
| Document | `CLAIM#<id>` | `DOC#<id>` | s3_key, mime, sha256, source, extracted (bool) |
| Config | `CONFIG#routing` | `v#<n>` | thresholds JSON, activated_by, activated_at (hot-reload; old versions retained → routing decisions are reproducible against the config version that made them) |

**GSIs.**
GSI1 `(gsi1pk = ENTITY#<type>#<status>, gsi1sk = updated_at)` → queue screens: claims by state, approvals pending by SLA.
GSI2 `(gsi2pk = ASSIGNEE#<user_id>, gsi2sk = sla_at)` → "my work" views.
GSI3 `(gsi3pk = CLAIMANT#<id>, gsi3sk = loss_date)` → claim-history tool, duplicate exact-match.

**Access-pattern check (design-by-query, the DynamoDB discipline reviewers look for):** claim detail = `Query PK=CLAIM#id` (one query returns meta + events + decisions + docs + msgs, already time-ordered — the Glass Cockpit is a single round trip); inbox = GSI1 `APPR#pending` sorted by SLA; tool forensics = `Query PK=WF#exec`; auditor export = `Query PK=AUDIT#date`.

## Equivalent Relational Schema (if you'd rather demo SQL)

```sql
CREATE TABLE users (id UUID PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT,
  role TEXT CHECK (role IN ('ops_manager','adjuster','siu','admin')),
  approval_limit NUMERIC(12,2), created_at TIMESTAMPTZ DEFAULT now());

CREATE TABLE sessions (id UUID PRIMARY KEY, user_id UUID REFERENCES users,
  jwt_id TEXT, ip INET, expires_at TIMESTAMPTZ);

CREATE TABLE claims (id TEXT PRIMARY KEY, state TEXT NOT NULL, workflow TEXT,
  line TEXT, peril TEXT, severity SMALLINT, fraud_score NUMERIC(3,2),
  confidence NUMERIC(3,2), completeness NUMERIC(3,2), amount_est NUMERIC(12,2),
  reserve NUMERIC(12,2) DEFAULT 0, paid NUMERIC(12,2) DEFAULT 0,
  claimant_id TEXT, policy_id TEXT, assignee UUID REFERENCES users,
  sla_at TIMESTAMPTZ, version INT DEFAULT 0, updated_at TIMESTAMPTZ);
CREATE INDEX claims_by_state ON claims(state, updated_at);

CREATE TABLE claim_events (id BIGSERIAL PRIMARY KEY, claim_id TEXT REFERENCES claims,
  ts TIMESTAMPTZ NOT NULL, type TEXT NOT NULL, actor JSONB, data JSONB, trace_id TEXT);
CREATE INDEX events_by_claim ON claim_events(claim_id, ts);

CREATE TABLE conversations (id BIGSERIAL PRIMARY KEY, claim_id TEXT REFERENCES claims,
  ts TIMESTAMPTZ, direction TEXT, channel TEXT, author TEXT, body TEXT, template_id TEXT);

CREATE TABLE workflow_executions (exec_id TEXT PRIMARY KEY, claim_id TEXT REFERENCES claims,
  workflow TEXT, engine_ref TEXT, status TEXT, phase TEXT, replan_count SMALLINT DEFAULT 0,
  token_budget_used INT DEFAULT 0, started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ);

CREATE TABLE tool_calls (id BIGSERIAL PRIMARY KEY, exec_id TEXT REFERENCES workflow_executions,
  seq INT, tool TEXT NOT NULL, risk_tier SMALLINT, args JSONB, args_hash TEXT,
  idempotency_key TEXT UNIQUE, status TEXT, result JSONB, error_code TEXT,
  latency_ms INT, retries SMALLINT DEFAULT 0, cached BOOL DEFAULT false, ts TIMESTAMPTZ);

CREATE TABLE agent_decisions (id BIGSERIAL PRIMARY KEY, claim_id TEXT REFERENCES claims,
  ts TIMESTAMPTZ, decision_type TEXT, model TEXT, prompt_hash TEXT, output JSONB,
  confidence NUMERIC(3,2), alternatives JSONB, citations JSONB, guardrails JSONB,
  tokens_in INT, tokens_out INT, latency_ms INT, trace_id TEXT);

CREATE TABLE approvals (id UUID PRIMARY KEY, claim_id TEXT REFERENCES claims,
  requested_action JSONB, risk_tier SMALLINT, confidence NUMERIC(3,2), status TEXT,
  sla_at TIMESTAMPTZ, resolved_by UUID REFERENCES users, resolution TEXT,
  delta JSONB, reason_code TEXT, created_at TIMESTAMPTZ, resolved_at TIMESTAMPTZ);

CREATE TABLE audit_log (id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ DEFAULT now(),
  actor TEXT, action TEXT, subject TEXT, before_hash TEXT, after_hash TEXT, ip INET);
-- append-only: REVOKE UPDATE, DELETE ON audit_log FROM app_role;
```

Either store works; the point the schema makes is identical: **decisions, tool calls, approvals, and overrides are first-class persisted entities with their own lifecycles — not log lines.** That's the difference between a system you can audit and a system you can only believe.

---

# PART 7 — OBSERVABILITY

## The Logging Contract

One structured-JSON envelope, emitted by every component, with `trace_id` minted at intake and propagated through SFN context, SQS message attributes, and LLM-call wrappers — so a single Logs Insights query reconstructs any claim end-to-end:

```json
{"ts":"2026-06-11T10:02:14.211Z","level":"INFO","trace_id":"trc_9f2","claim_id":"CLM-2026-00417",
 "component":"router","event":"claim.routed","data":{"workflow":"W1","rule_id":"R-03",
 "inputs":{"fraud":0.08,"severity":1,"amount":412,"conf":0.91},"config_version":7},
 "_aws":{"CloudWatchMetrics":[{"Namespace":"AdjusterZero","Metrics":[{"Name":"RoutedW1","Unit":"Count"}]}]}}
```

(EMF: the metric rides the log line — no second pipeline.)

**What gets logged, by category:**

| Category | Captured fields | Where |
|---|---|---|
| User requests | route, user, latency, status, claim_id | api-handler access log |
| Agent decisions | decision_type, model, prompt_hash, output, **confidence, alternatives, citations**, tokens, latency, guardrail results | `DEC#` items + log |
| Workflow selections | rule_id fired, full router inputs, config_version | `claim.routed` event |
| Tool executions | tool, args_hash, risk_tier, status, latency, retries, error_code, cached, idempotency_key | `TOOL#` items + log |
| Failures | error chain, retry trajectory, DLQ message id, compensation actions taken | `claim.failed` + DLQ + alarm |
| Human actions | approval resolution, **structured delta on modify**, reason_code | `APPR#` + audit log |

## Hallucination-Risk Instrumentation

You cannot log "hallucination" directly; you log its measurable proxies and alarm on them:

1. **Schema-violation rate** — % of LLM outputs failing JSON Schema validation (pre-repair). The cheapest, most honest model-quality signal in production. Alarm > 5%.
2. **Citation coverage** — % of determinative assertions in coverage/denial outputs that reference retrieved chunk IDs. < 100% on a determinative claim ⇒ confidence floored ⇒ human review. Logged per decision.
3. **Grounding floor** — top retrieval score behind each citation; a "citation" to a 0.31-relevance chunk is decoration, and the validator treats it as uncited.
4. **Numeric-consistency checks** — extracted `claimed_amount` vs. document OCR totals vs. estimator output; divergence > 15% ⇒ `NUMERIC_MISMATCH` flag ⇒ no STP.
5. **Self-consistency sampling (T2 paths only)** — classification re-sampled k=3 at temperature on money-adjacent decisions; disagreement collapses confidence. Spend the tokens only where wrongness costs money.
6. **Override-rate-by-confidence** — the ultimate lagging indicator: if humans overturn 30% of proposals the agent scored 0.9, your confidence is fiction and the calibration chart says so publicly.
7. **Nightly canary evals** — 50 golden claims with labeled routes/outcomes replayed via Step Functions; report pass rate + route confusion matrix; alarm on regression. Prompt changes ship behind this gate or not at all.

## Dashboards

**D1 — Operations (CloudWatch + in-app S5):** intake rate, funnel (received → triaged → W1/W2/W3/W4/W5 → settled), queue depths & DLQ size, REVIEW_PENDING aging vs. SLA, p50/p95 intake→decision latency, tool failure-rate table (top-N by error_code).
**D2 — Agent Quality:** schema-violation rate by model/prompt_hash, citation coverage trend, **confidence-calibration chart (predicted vs. human-agreement by decile)**, override rate + override-reason Pareto, eval pass-rate sparkline, route confusion matrix.
**D3 — Cost:** tokens by model and by component, cost-per-claim distribution, cache hit rates (prompt + tool), per-claim token-budget breaches.

## KPIs

| KPI | Definition | Target (synthetic book) |
|---|---|---|
| STP rate | % claims settled with zero human touch | 35–45% |
| Cycle time | median intake→decision | < 5 min (W1 < 2 min) |
| Override rate | % agent proposals modified/rejected | < 10%, trending down |
| Calibration error | mean \|confidence − agreement\| across deciles | < 0.10 |
| Unauthorized-payment count | payments lacking gate/approval ref | **0, structurally** |
| Tool success rate | non-error completions / attempts | > 98% |
| Schema-violation rate | invalid LLM outputs pre-repair | < 3% |
| Cost per claim | tokens + infra amortized | < $0.10 |
| Eval pass rate | golden-set nightly | > 92%, no silent regressions |
| Escalation precision | % escalations humans deem warranted | > 80% (crying wolf erodes trust) |

---

# PART 8 — INTERVIEW VALUE: THE CEO/CTO READ

**Why it demonstrates AI-Lead capability.** The scarce skill in 2026 is not prompting — it's **drawing the line between probabilistic and deterministic responsibility** and then enforcing that line in architecture. This project *is* that line, made visible: the LLM extracts, classifies, plans, and drafts; rules route; a state machine executes; humans sign for money. An AI Lead's actual job is deciding where models are allowed to be wrong and making wrongness cheap, detectable, and reversible. Every screen of this product is that decision rendered in pixels.

**Architectural decisions that stand out.**
- *The LLM proposes, the orchestrator disposes* — plans are data, validated against allow-lists and invariants before execution. No "agent loop until done."
- *Routing as a pure, versioned, replayable function* — policy changes are testable against history before they touch production. That's governance, not vibes.
- *Risk-tiered tools with structural gates* — `payment_execute` without an approval/gate reference doesn't fail at runtime; it's **unrepresentable**. Safety by construction beats safety by prompt.
- *Event-sourced core* — audit trail, dashboard feed, and replay/eval substrate are one mechanism, not three features.
- *Fail-closed compliance* — sanctions service down ⇒ all payments halt. Choosing availability sacrifices correctly is senior-engineer territory.
- *HITL as a designed product surface* — an approval inbox with evidence, confidence, alternatives, and captured override deltas, not a Slack ping.

**Engineering-maturity signals.** Idempotency keys and reconcile-before-retry on payments; sagas/compensation; DLQs with forensics; bounded re-planning and per-claim token budgets (cost incidents are incidents); config versioning so every routing decision is reproducible; an eval gate in front of prompt changes; degraded-mode rules ("no STP while a fraud control is down"). Each one says: *this person has been paged before, or thinks like someone who has.*

**What specifically impresses a CTO.** Three artifacts, in order: (1) the **calibration chart** — almost no candidate measures whether their agent's confidence means anything, and it's the chart that justifies raising autonomy thresholds with data; (2) the **decision log schema** — confidence, alternatives, citations, guardrail results as persisted entities, i.e., the answer to "what happens when the model is wrong?" before the question is asked; (3) the **refusal demo** — Journey B, where the agent declines to pay and cites the lapse clause. Anyone can demo capability; demonstrating *restraint with receipts* is what makes a CTO lean forward.

---

# PART 9 — MVP ROADMAP (four weekends, solo)

The discipline that makes this shippable: **the vertical slice ships in Week 1 and never breaks again.** Each subsequent week swaps a naive internal for the production pattern. Equally important is the cut list — written down so scope creep has to fight in daylight.

**Not building, ever (MVP):** real payment rails, real email delivery (console "sent" log), multi-tenant orgs, mobile, fine-tuning, real OCR (synthetic FNOLs carry text + structured ground truth), W3 beyond the hand-off packet (SIU tooling is a black hole).

## Week 1 — The Vertical Slice (it works end-to-end, naively)
- Synthetic data generator v0: policies, claimants, and parameterized FNOLs (clean glass claim, lapsed policy, missing docs) — *built first; it's your test suite and your demo reel*.
- Monolith FastAPI Lambda + DynamoDB single table; intake endpoint → Claim Aggregate + event log.
- Planner v0 (extract + classify, schema-validated, one repair retry); Router v0 (rule table, R-03/R-99 only); Executor v0: the 200-line in-process interpreter over JSON workflow definitions.
- Tools: `policy_lookup`, `coverage_check` (rules-only stub), `repair_cost_estimator`, `payment_execute` (mock, idempotent), `customer_comm_send` (draft mode).
- Dashboard: claims queue + claim detail with a plain event timeline. Deployed to AWS on day two — deployment friction discovered in Week 1 costs days; discovered in Week 4 it costs the project.
- **Demo at week's end:** Journey A, naive edition.

## Week 2 — Real Routing, Real Orchestration, Real Humans
- Full rule table R-00…R-99; workflows W1/W2/W4 live (W5 = escalate-with-packet stub).
- Tool registry with JSON Schema validation, risk tiers, uniform error envelope; add `fraud_signal_scan` (rules-only), `claim_history`, `duplicate_claim_check` (exact), `document_request_create`, `escalate_to_human`, `reserve_set`.
- Port the interpreter to **Step Functions Standard** with `waitForTaskToken`; EventBridge bus + Scheduler (reminders, SLA timers); SQS tool queue + DLQ.
- Approval Inbox UI with approve/modify/reject and structured-delta capture.
- **Demo:** Journeys B and D — the refusal and the approver's day.

## Week 3 — Grounding, Fraud, and the Glass Cockpit
- RAG layer: guideline corpus (write ~12 short guideline docs yourself), chunk → embed → index (cheap-profile FAISS layer is fine); `guideline_search`; upgrade `coverage_check` to cited determinations with citation-coverage validation.
- Fraud path: semantic duplicate detection, `weather_event_verify`, LLM-assisted signal scan, R-06 tie-break with logged alternatives; W3 hand-off packet.
- Observability: decision records as first-class items, trace-stitched timeline, the full Glass Cockpit center pane (expandable tool calls, decisions with confidence/alternatives/citations), Agent Console event stream.
- **Demo:** Journey C — the fraud catch, with evidence on screen.

## Week 4 — Trust, Polish, and the Sales Layer
- Eval harness: 50 golden claims, nightly replay, route confusion matrix, pass-rate trend; wire as a manual "Run Evals" button in Admin too (judges love a live eval run).
- Analytics screen: KPI tiles, funnel, **calibration chart** (seed it by adjudicating ~60 synthetic approvals yourself — your own overrides are the data), cost-per-claim meter.
- Hardening pass: payment reconcile-before-retry, compensation path, token budgets, degraded-mode rule, config versioning.
- The sales layer: README with the Part 5 diagram, a 3-minute scripted screen recording (Journeys A → B → C → D in that order), one-page architecture-decisions doc ("what the LLM is *not* allowed to do" as the headline section), seeded demo environment with one-click claim injection.

If a weekend evaporates, cut in this order: calibration chart seeding → W4 reminders → Agent Console → semantic duplicates. **Never cut:** Step Functions, the approval inbox, the decision log, Journey B.

---

# PART 10 — DIFFERENTIATION: WHY THIS BURIES THE USUAL PORTFOLIO

Be honest about what the usual projects actually prove, because the CTO reviewing you will be.

**ChatGPT clone.** Proves you can read API documentation and center a div. No state beyond a transcript, no side effects, no failure that matters, no decision anyone has to stand behind. It demonstrates consumption of AI, not engineering of it. A CTO sees forty of these a quarter and remembers none.

**RAG chatbot.** Retrieval is table stakes — a 2023 skill performing as a 2026 differentiator, which it isn't. Structurally, a RAG bot *answers*; it never *acts*, so it never needs idempotency, compensation, approval gates, or an audit trail, and its worst failure is a wrong sentence. Adjuster Zero contains a RAG layer as one subsystem among nine — and uses it the hard way, as grounding for consequential decisions with enforced citations, not as a search box with vibes.

**PDF Q&A assistant.** A feature wearing a product's clothes. One workflow, zero routing, zero state machine, zero tools with consequences, zero humans in any loop. The gap between "answers questions about a document" and "extracts a document, verifies it against systems of record, and conditionally moves money under audit" is the gap between a weekend tutorial and an engineering portfolio.

**AI wrapper startup.** The CTO's first question to any wrapper is *"what happens when the model is wrong?"* — and the wrapper's honest answer is "the user notices, hopefully." Adjuster Zero's entire architecture is a better answer: wrongness is bounded by risk tiers, caught by validators and calibration, reversed by compensation, escalated with evidence, and priced on a dashboard. That question stops being a threat and becomes your demo script.

**The blunt summary.** Chat projects demonstrate that you can *call* a model. This project demonstrates that you can be **trusted to put a model inside a business process that touches money** — with the judgment to know what it must never be allowed to do, the engineering to make violations unrepresentable, and the instrumentation to prove both. That is the AI-Lead job description, restated as a working system. Everything else on the list is a feature; this is evidence.

---

## Appendix — One-Paragraph Pitch (for the README header)

> **Adjuster Zero** is an autonomous insurance-claims operations agent. It ingests a First Notice of Loss, extracts and verifies it against policy systems, routes it across five workflows (straight-through payment, standard adjudication, fraud investigation, information request, high-severity escalation) via a deterministic, replayable rule engine fed by LLM classification; executes investigation and settlement through 18 risk-tiered, schema-validated tools orchestrated by AWS Step Functions; pays small clean claims with zero human touch and pauses on task tokens for human approval everywhere else; and records every decision — confidence, alternatives, citations, overrides — in an event-sourced audit log rendered live on a transparent operations dashboard. Built solo in four weekends on Lambda, DynamoDB, EventBridge, SQS, and Bedrock for roughly the price of a coffee per 500 claims.

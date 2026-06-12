# Demo script — the 7-minute interview walkthrough

> Goal: show **visible orchestration** and **restraint with receipts**, not a chatbot.
> All data is synthetic. Everything runs at ~€0/month.

## T-30 minutes (warm-up checklist)
1. Trigger the GitHub Actions **keep-alive** (or hit `/healthz`) so Supabase + Cloud Run are warm.
2. Admin: **Reset demo data** (optional) so the queue is clean.
3. Analytics → check the **RPD budget meter** (>60 flash-lite calls available).
4. Open three tabs: **Queue**, **Approval inbox**, **Analytics**. Log in as an operator.
5. Plan B: the README GIFs / 3-minute recording. Plan C: `make demo` locally.

## The 7 minutes

**0:00–0:30 — Frame it.** Queue is empty. "This is an autonomous claims department with a
paper trail. I'll inject three claims and you'll watch the agent decide. The thesis: the LLM
proposes; a deterministic state machine disposes. Money never moves without a hard gate or a
human signature."

**0:30–2:30 — Journey A, the 90-second settle.** Click **Inject clean claim**. Narrate the
glass cockpit live: per-field extraction confidence, classification with alternatives,
"**rule R-03 fired → W1**", the read-only investigation tools, the citation chip on coverage,
the tier-0 policy gate, the payment, **CLOSED** in seconds. Point at the **"Chose NOT to"**
panel — the tools the planner skipped and why.

**2:30–4:00 — Journey B, the refusal.** Click **Inject lapsed policy**. The agent declines,
cites the lapse clause, drafts the denial — and *still* routes to **REVIEW_PENDING** because
denying is consequential. Switch to the **Approval inbox**, approve it, and show the claim
resume to **DENIED**. "That pause is human-in-the-loop via a durable `interrupt()` +
checkpointer — the same pattern as Step Functions `waitForTaskToken`, at €0 while paused."
(Optional: kill and restart the agent service while it's paused, then approve — it still resumes.)

**4:00–5:30 — Journey C, the fraud catch.** Click **Inject fraud suspect**. Fraud score **0.81**
with itemized signals and evidence, routed to **W3 / SIU**. "From this state, the payment path
is unreachable — by construction, not by prompt." Show the hand-off packet and the duplicate
evidence (semantic, not just exact).

**5:30–7:00 — The numbers.** Analytics: **STP rate**, **override rate**, the
**confidence-calibration chart**, **cost per claim**. Click **Run evals** → route-accuracy on
the 50-claim golden set. Close with: "All of this runs at €0/month; here's the equivalent AWS
design for enterprise scale" — open the README mapping table.

## The viewer link
Public, read-only (Supabase RLS `viewer` role): the recruiter can explore alone afterward.
Put the link in the CV and LinkedIn — the portfolio works while you sleep.

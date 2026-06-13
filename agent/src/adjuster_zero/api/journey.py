"""Build a claim's *journey* — an ordered, replayable list of steps, each with the
INPUT it received, the OUTPUT it produced, and a plain-language explanation of what
happened and why. This is a pure projection over the already-persisted trace
(decisions + tool calls + events); it runs no LLM and triggers no side effect, so it
is safe, free, and deterministic. It powers the step-by-step walkthrough page.
"""

from __future__ import annotations

from typing import Any

# ── phases (the diagram's lanes), in canonical order ──────────────────────────
PHASES: list[tuple[str, str]] = [
    ("RECEIVE", "Receive"),
    ("EXTRACT", "Extract"),
    ("CLASSIFY", "Classify"),
    ("INVESTIGATE", "Investigate"),
    ("ROUTE", "Route"),
    ("EXECUTE", "Execute"),
    ("RESOLVE", "Resolve"),
]

# Tools that gather routing inputs (read-only, T0) vs. tools that act (T1/T2).
_INVESTIGATE_TOOLS = {
    "policy_lookup", "coverage_check", "repair_cost_estimator", "weather_event_verify",
    "guideline_search", "claim_history", "duplicate_claim_check", "fraud_signal_scan",
}

# Per-tool: (friendly title, what-it-did explanation).
_TOOL_DOC: dict[str, tuple[str, str]] = {
    "policy_lookup": (
        "Look up the policy",
        "A read-only (T0) data read: is the policy active at the loss date, and which "
        "coverages does it carry? No LLM here — just facts the router will need."),
    "coverage_check": (
        "Pre-screen coverage (deterministic)",
        "A rules pre-screen against the policy's coverages and exclusions. Its result "
        "is handed to the grounded LLM determination as a starting point — never the "
        "final word on its own."),
    "repair_cost_estimator": (
        "Estimate the repair cost",
        "A deterministic estimate of the loss amount. This number is what the auto-pay "
        "ceiling is later tested against (R-03 straight-through)."),
    "weather_event_verify": (
        "Corroborate with weather",
        "For weather perils, cross-check a (mock NOAA) event near the loss date and "
        "place. If this control is unavailable the claim is capped — fail-closed."),
    "guideline_search": (
        "Retrieve the governing guidelines (RAG)",
        "Hybrid retrieval — keyword search fused with vector similarity — pulls the "
        "specific guideline passages the coverage determination is then required to "
        "cite. This is the 'R' in agentic RAG."),
    "claim_history": (
        "Pull the claimant's history",
        "Prior-claim count, first-seen flag, recent coverage increase — all inputs to "
        "the fraud score."),
    "duplicate_claim_check": (
        "Check for duplicate claims",
        "Exact match plus semantic (embedding) similarity against prior claims. An "
        "exact hard match alone sends the claim straight to SIU (rule R-00)."),
    "fraud_signal_scan": (
        "Score the fraud signals",
        "A deterministic weighted scan over every signal gathered above — duplicates, "
        "implausible narrative, claim frequency — collapsed into one fraud_score the "
        "router thresholds. The weights are fixed and auditable, not learned."),
    "reserve_set": (
        "Set the reserve (T1)",
        "A reversible write: ring-fence the estimated amount on the books before any "
        "money moves. If payment later fails, this is rolled back (the saga)."),
    "sanctions_watchlist_check": (
        "Mandatory sanctions screen",
        "Fail-closed by construction: if this screen is unavailable, EVERY payment is "
        "blocked and the claim is parked for a human — the outage can't open the gate."),
    "payment_execute": (
        "Execute the payment (T2)",
        "The highest-risk action in the whole system. It is structurally gated: the "
        "call REQUIRES an approval_ref or a policy_gate_ref as a constructed field, so "
        "an unauthorized payment is literally unrepresentable — not merely checked at "
        "runtime."),
    "customer_comm_send": (
        "Draft the customer letter",
        "Outbound communication. In send-mode it's a T2 gated action; here it writes a "
        "draft to the database and console — never a real email (this is a showroom)."),
    "document_request_create": (
        "Request the missing documents",
        "W4: ask the claimant for exactly the intake facts we found missing, then pause "
        "the claim durably until they arrive — it can resume days later, same state."),
    "denial_letter_draft": (
        "Draft the denial letter",
        "A cited, plain-language denial drafted for a human to review before it's sent."),
    "siu_handoff_packet": (
        "Build the SIU hand-off packet",
        "Bundle the evidence for the Special Investigations Unit. From here no payment "
        "path is even reachable, by construction."),
}

_ACTOR_FOR = {"orchestrator": "orchestrator", "llm": "llm", "tool": "tool", "human": "human"}


def _fnol(claim: dict[str, Any]) -> str:
    return claim.get("fnol_text") or claim.get("fnol") or ""


def _money(v: Any) -> str:
    return "—" if v in (None, "") else f"${float(v):,.2f}"


def _step(idx: int, phase: str, actor: str, title: str, subtitle: str,
          in_label: str, in_value: Any, out_label: str, out_value: Any,
          explanation: str, meta: dict[str, Any] | None = None,
          prompt: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "index": idx, "phase": phase, "actor": _ACTOR_FOR.get(actor, actor),
        "title": title, "subtitle": subtitle,
        "input": {"label": in_label, "value": in_value},
        "output": {"label": out_label, "value": out_value},
        "explanation": explanation, "meta": meta or {},
        # The verbatim request we sent to the LLM (None for tool / pure-rule steps).
        "prompt": prompt,
    }


def _prompt_of(d: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the persisted request (system + user prompt) off an LLM decision."""
    user, system = d.get("prompt"), d.get("system_prompt")
    if not user and not system:
        return None
    return {"system": system, "user": user}


def _llm_subtitle(d: dict[str, Any]) -> str:
    bits = []
    if d.get("model"):
        bits.append(str(d["model"]))
    tin, tout = d.get("tokens_in"), d.get("tokens_out")
    if tin is not None or tout is not None:
        bits.append(f"{(tin or 0) + (tout or 0)} tok")
    if d.get("latency_ms"):
        bits.append(f"{int(d['latency_ms'])} ms")
    if d.get("confidence") is not None:
        bits.append(f"conf {d['confidence']}")
    return " · ".join(bits)


def _extract_step(idx: int, d: dict[str, Any], fnol: str) -> dict[str, Any]:
    out = d.get("output", {})
    fields = {f["name"]: f.get("value") for f in out.get("fields", [])}
    det = out.get("deterministic_completeness")
    miss = out.get("deterministic_missing", out.get("missing_required", []))
    body = {
        "extracted_fields": fields,
        "llm_self_score (ignored for routing)": out.get("overall_completeness"),
        "deterministic_completeness": det,
        "missing_intake_facts": miss,
    }
    expl = (
        "The LLM read the free-text notice and proposed typed fields, each with its "
        "own confidence — the LLM proposes. But the orchestrator disposes: it does NOT "
        "trust the LLM's self-scored completeness (shown here for transparency). It "
        f"recomputes completeness deterministically over the required intake facts "
        f"(policy, date, location): {det}"
        + (f". Still missing: {', '.join(miss)} → this will route to the information "
           "request loop (W4)." if miss else " — all present.")
    )
    return _step(idx, "EXTRACT", "llm", "Extract structured fields from the FNOL",
                 _llm_subtitle(d), "Raw FNOL text", fnol, "Typed fields + completeness",
                 body, expl, {"model": d.get("model"), "tokens": (d.get("tokens_in") or 0)
                 + (d.get("tokens_out") or 0), "latency_ms": d.get("latency_ms")},
                 prompt=_prompt_of(d))


def _classify_step(idx: int, d: dict[str, Any], fnol: str) -> dict[str, Any]:
    out = d.get("output", {})
    expl = (
        "The LLM proposed the line of business, peril, severity and complexity — with "
        "alternatives and a confidence. This is still only data: nothing has been "
        "routed or actioned. A low confidence here can itself slow the claim down.")
    return _step(idx, "CLASSIFY", "llm", "Classify the loss", _llm_subtitle(d),
                 "FNOL text + extracted fields", fnol, "Classification",
                 {"line": out.get("line"), "peril": out.get("peril"),
                  "severity": out.get("severity"), "complexity": out.get("complexity"),
                  "confidence": out.get("confidence"), "alternatives": out.get("alternatives")},
                 expl, {"model": d.get("model"), "confidence": out.get("confidence")},
                 prompt=_prompt_of(d))


def _action_step(idx: int, d: dict[str, Any], fnol: str) -> dict[str, Any]:
    out = d.get("output", {})
    if "plausible" in out or "coherence" in out:  # narrative plausibility screen
        implausible = out.get("plausible") is False
        verdict = ("It was judged IMPLAUSIBLE — a fraud signal fires here that pushes the "
                   "claim out of the auto-pay band and toward a human."
                   if implausible else
                   "It was judged plausible, so this screen adds no fraud signal.")
        expl = (
            "A plausibility screen: the LLM judged whether the stated loss cause is "
            f"physically coherent. {verdict} (This is exactly the control that stops an "
            "'alien hit my windshield' claim from auto-paying.)")
        return _step(idx, "INVESTIGATE", "llm", "Screen the narrative for plausibility",
                     _llm_subtitle(d), "FNOL narrative", fnol,
                     "Plausibility verdict",
                     {"plausible": out.get("plausible"), "coherence": out.get("coherence"),
                      "anomalies": out.get("anomalies"), "reason": out.get("reason")},
                     expl, {"model": d.get("model"), "confidence": out.get("confidence")},
                     prompt=_prompt_of(d))
    # grounded coverage determination — describe what the recorded values actually show.
    conf = d.get("confidence")
    cites = d.get("citations") or []
    if cites and conf != 0.5:
        outcome = (f"Here it cited {cites} at confidence {conf} — citation coverage was "
                   "satisfied, so the determination stands on its own.")
    elif conf == 0.5:
        outcome = ("Here the determination had no valid citation, so the control fired: "
                   "confidence was floored to 0.5 and the claim sent to a human.")
    else:
        outcome = f"Here: citations = {cites or 'none'}, confidence = {conf}."
    expl = (
        "RAG-grounded coverage determination: the LLM decides covered / not covered, "
        "but it MUST cite the retrieved guideline chunks. Citation coverage is enforced "
        f"— an uncited determinative call is floored to 0.5 confidence and sent to a "
        f"human. {outcome}")
    return _step(idx, "INVESTIGATE", "llm", "Determine coverage (grounded + cited)",
                 _llm_subtitle(d), "Policy facts + retrieved guideline chunks",
                 {"covered_prescreen": out.get("covered"), "query": "peril + policy status"},
                 "Coverage determination",
                 {"covered": out.get("covered"), "confidence": conf,
                  "citations": cites, "exclusions": out.get("exclusions_triggered"),
                  "guardrails": d.get("guardrails")},
                 expl, {"model": d.get("model"), "confidence": conf, "citations": cites},
                 prompt=_prompt_of(d))


def _route_step(idx: int, d: dict[str, Any]) -> dict[str, Any]:
    out = d.get("output", {})
    expl = (
        "The deterministic router — a pure, unit-tested function — evaluated rules "
        "R-00..R-99 top-down over these typed inputs. First match wins. The LLM has no "
        f"vote here (its only influence is the narrow R-06 tiebreak band). Rule "
        f"{out.get('rule_id')} fired → {out.get('workflow')}: {out.get('rationale')}")
    return _step(idx, "ROUTE", "orchestrator", "Route — pure rules over typed inputs",
                 "deterministic · 0 tokens", "RouterInput snapshot", out.get("inputs", {}),
                 "Routing decision",
                 {"workflow": out.get("workflow"), "rule_id": out.get("rule_id"),
                  "rationale": out.get("rationale"), "needs_tiebreak": out.get("needs_tiebreak")},
                 expl, {"rule_id": out.get("rule_id")})


def _tiebreak_step(idx: int, d: dict[str, Any]) -> dict[str, Any]:
    out = d.get("output", {})
    expl = (
        "The R-06 ambiguous fraud band — the ONE place the LLM influences routing. "
        "Grounded in fraud-screening guidelines, it picked a workflow, and the choice "
        "is persisted with its alternatives and rationale so the call is auditable.")
    return _step(idx, "ROUTE", "llm", "R-06 tiebreak (the one LLM routing call)",
                 _llm_subtitle(d), "Fraud score + signals + guidelines",
                 {"context": "fraud_score + signals"}, "Tiebreak choice",
                 {"workflow": out.get("workflow"), "rationale": out.get("rationale"),
                  "confidence": out.get("confidence"), "alternatives": out.get("alternatives")},
                 expl, {"model": d.get("model"), "confidence": out.get("confidence")},
                 prompt=_prompt_of(d))


def _gate_ref(args: dict[str, Any]) -> str | None:
    auth = args.get("authorization")
    if isinstance(auth, dict):
        ref = auth.get("policy_gate_ref") or auth.get("approval_ref")
        if ref:
            kind = "policy_gate_ref" if auth.get("policy_gate_ref") else "approval_ref"
            return f"{kind}={ref}"
    return None


def _tool_step(idx: int, t: dict[str, Any]) -> dict[str, Any]:
    name = t.get("tool", "tool")
    phase = "INVESTIGATE" if name in _INVESTIGATE_TOOLS else "EXECUTE"
    title, expl = _TOOL_DOC.get(name, (name, "A registered tool call."))
    if name == "payment_execute":
        ref = _gate_ref(t.get("args", {}) or {})
        expl += (f" In this run the gate it carried was {ref}." if ref
                 else " (No authorization ref was recorded on this call.)")
    tier = t.get("risk_tier")
    subtitle = " · ".join(filter(None, [
        f"T{tier}" if tier is not None else None,
        "cached" if t.get("cached") else None,
        f"{int(t['latency_ms'])} ms" if t.get("latency_ms") else None,
        "ERROR" if t.get("status") == "error" else None,
    ]))
    return _step(idx, phase, "tool", title, subtitle, f"{name} args", t.get("args", {}),
                 "Tool result", t.get("result", t.get("error_code")), expl,
                 {"risk_tier": tier, "status": t.get("status"), "tool": name})


_TERMINAL = {
    "CLOSED": "The claim was paid and closed straight-through — no human touched it.",
    "DENIED": "The claim was denied with a cited reason; a human approved the denial first.",
    "ESCALATED": "The claim was escalated (e.g. to SIU). No payment path was reachable.",
    "REVIEW_PENDING": "The claim is parked for a human decision — the agent refused to "
                      "act on its own (a refusal is a correct outcome, not a failure).",
    "INFO_PENDING": "The claim is waiting on missing information from the claimant; it "
                    "will resume itself when the documents arrive.",
    "SETTLEMENT": "The claim reached settlement.",
}


def _resolve_step(idx: int, claim: dict[str, Any]) -> dict[str, Any]:
    state = claim.get("state", "—")
    expl = _TERMINAL.get(state, f"The claim ended in state {state}.")
    return _step(idx, "RESOLVE", "orchestrator", f"Resolve → {state}",
                 claim.get("workflow") or "", "Workflow outcome",
                 {"workflow": claim.get("workflow"), "rule_id": claim.get("rule_id")},
                 "Final state",
                 {"state": state, "paid": _money(claim.get("paid")),
                  "amount_est": _money(claim.get("amount_est")),
                  "fraud_score": claim.get("fraud_score")},
                 expl, {"rule_id": claim.get("rule_id")})


def build_journey(claim: dict[str, Any], events: list[dict[str, Any]],
                  decisions: list[dict[str, Any]], tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure projection of the persisted trace into an ordered list of teaching steps."""
    fnol = _fnol(claim)
    # True chronological replay: merge decisions + tool calls by their ISO timestamp
    # (each record is timestamped at write, so ts IS the causal order). Tie-break by the
    # executor's monotonic `seq` so concurrent tool calls keep their true order; the sort
    # is stable, so the result is deterministic given the same trace.
    timeline = sorted(
        [{"kind": "decision", "ts": d.get("ts", ""), "seq": -1, "d": d} for d in decisions]
        + [{"kind": "tool", "ts": t.get("ts", ""), "seq": t.get("seq", 0), "t": t} for t in tool_calls],
        key=lambda x: (x["ts"], x["seq"]))

    steps: list[dict[str, Any]] = []
    # Step 0 — RECEIVE (synthetic; the raw input before any interpretation).
    steps.append(_step(
        0, "RECEIVE", "orchestrator", "Receive the First Notice of Loss", "intake",
        "Submitted FNOL", fnol or "(photo intake)", "New claim aggregate",
        {"claim_id": claim.get("id"), "claimant_id": claim.get("claimant_id"),
         "policy_number": claim.get("policy_number")},
        "A claim arrived as free text (or a photo's description). Nothing is interpreted "
        "yet — and from here the agent never acts on this text directly; it first turns "
        "it into typed, validated data."))

    for item in timeline:
        i = len(steps)
        if item["kind"] == "decision":
            d = item["d"]
            dt = d.get("decision_type")
            if dt == "extract":
                steps.append(_extract_step(i, d, fnol))
            elif dt == "classify":
                steps.append(_classify_step(i, d, fnol))
            elif dt == "action":
                steps.append(_action_step(i, d, fnol))
            elif dt == "route":
                steps.append(_route_step(i, d))
            elif dt == "tiebreak":
                steps.append(_tiebreak_step(i, d))
        else:
            steps.append(_tool_step(i, item["t"]))

    steps.append(_resolve_step(len(steps), claim))

    # Mark which phases actually occurred, for the diagram.
    seen = {s["phase"] for s in steps}
    phases = [{"key": k, "label": lbl, "active": k in seen} for k, lbl in PHASES]
    return {
        "claim_id": claim.get("id"),
        "final": {"state": claim.get("state"), "workflow": claim.get("workflow"),
                  "rule_id": claim.get("rule_id"), "paid": claim.get("paid"),
                  "amount_est": claim.get("amount_est"), "fraud_score": claim.get("fraud_score")},
        "phases": phases,
        "steps": steps,
    }

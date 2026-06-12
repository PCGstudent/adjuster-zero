"""The claim lifecycle as a LangGraph StateGraph — the agent's spine (thesis 1).

intake → extract → classify → investigate → route → one of:
  W1 → w1_execute → settle → close          (straight-through, tier-0 gate)
  W2 → w2_propose → w2_await (interrupt) →   (human approval: pay / deny / reject)
  W3 → w3_fraud   (escalate to SIU; NO payment edge)
  W4 → w4_request → w4_await (interrupt) → re-triage on document arrival
  W5 → w5_escalate (senior adjuster packet)

The LLM proposes (extract/classify/draft letter); the graph disposes (routes,
gates, executes, pauses for humans). Every transition writes a claim_events row
atomically with the projection (thesis 5). Human approval uses LangGraph
interrupt() + the Postgres checkpointer — the durable analogue of Step Functions
waitForTaskToken; a paused claim survives an agent-service restart (thesis: HITL).
Bounded autonomy (thesis 6): token-budget escalation + replan counter on the W4
info loop.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..config import get_settings
from ..domain.aggregate import (
    ClaimAggregate,
    ClassAlternative,
    Classification,
    Coverage,
    Extraction,
    PolicyStatus,
)
from ..domain.events import EventType, claim_event
from ..domain.states import ClaimState, Workflow
from ..llm import GeminiClient
from ..llm.errors import EscalateToHuman
from ..persistence.store import ApprovalRecord, ClaimStore, DecisionRecord
from ..planner import (
    apply_citation_floor,
    classify_claim,
    decide_tiebreak,
    determine_coverage,
    draft_letter,
    extract_fnol_fields,
)
from ..router import RouterInput, RoutingConfig, route
from ..tools import ToolExecutor
from ..tools.schemas import PaymentAuthorization


@dataclass
class LifecycleDeps:
    store: ClaimStore
    planner: GeminiClient
    executor: ToolExecutor
    routing_config: RoutingConfig
    config_version: int | None = None
    # When True the graph runs the grounded (RAG + LLM) coverage determination and
    # the R-06 tiebreak; otherwise it uses rules-only coverage + conservative W2.
    ground_coverage: bool = False


class BudgetExhausted(EscalateToHuman):
    def __init__(self, used: int, budget: int) -> None:
        super().__init__("TOKEN_BUDGET_EXHAUSTED", f"used {used} > budget {budget}")


def build_lifecycle_graph(deps: LifecycleDeps) -> StateGraph:
    store = deps.store
    settings = get_settings()

    async def _commit(agg: ClaimAggregate, type: EventType, **data: Any) -> None:
        """Atomically persist the updated projection AND its event (thesis 5)."""
        ev = claim_event(agg.id, type, component="executor", data=data, trace_id=agg.trace_id)
        await store.commit_transition(agg, ev)

    def _check_budget(agg: ClaimAggregate) -> None:
        if agg.token_budget_used > settings.claim_token_budget:
            raise BudgetExhausted(agg.token_budget_used, settings.claim_token_budget)

    # ── triage ───────────────────────────────────────────────────────────────
    async def intake(agg: ClaimAggregate) -> dict[str, Any]:
        agg2 = agg.model_copy(update={"state": ClaimState.RECEIVED})
        await _commit(agg2, EventType.RECEIVED, fnol_chars=len(agg.fnol_text))
        return {"state": ClaimState.RECEIVED}

    async def extract(agg: ClaimAggregate) -> dict[str, Any]:
        result, meta = await extract_fnol_fields(deps.planner, agg.fnol_text)
        fields = {f.name: f.value for f in result.fields if f.value is not None}
        field_conf = {f.name: f.confidence for f in result.fields}
        extraction = Extraction(
            fields=fields, field_confidence=field_conf,
            missing_required=result.missing_required, completeness=result.overall_completeness,
        )
        await store.record_decision(DecisionRecord(
            claim_id=agg.id, decision_type="extract", model=meta.model,
            output=result.model_dump(), confidence=result.overall_completeness,
            guardrails={"schema_ok": True, "repaired": meta.repaired},
            tokens_in=meta.tokens_in, tokens_out=meta.tokens_out, latency_ms=meta.latency_ms,
            trace_id=agg.trace_id,
        ))
        used = agg.token_budget_used + meta.tokens_in + meta.tokens_out
        updates: dict[str, Any] = {
            "extraction": extraction, "token_budget_used": used, "state": ClaimState.TRIAGE,
            "policy_number": fields.get("policy_number") or agg.policy_number,
        }
        agg2 = agg.model_copy(update=updates)
        await _commit(agg2, EventType.EXTRACTED, completeness=extraction.completeness,
                      missing=extraction.missing_required)
        _check_budget(agg2)
        return updates

    async def classify(agg: ClaimAggregate) -> dict[str, Any]:
        result, meta = await classify_claim(deps.planner, agg.fnol_text, agg.extraction.fields)
        classification = Classification(
            line=result.line, peril=result.peril, severity=result.severity,
            complexity=result.complexity, injury_flag=result.injury_flag,
            attorney_flag=result.attorney_flag, confidence=result.confidence,
            alternatives=[ClassAlternative(label=a.label, p=a.p) for a in result.alternatives],
        )
        await store.record_decision(DecisionRecord(
            claim_id=agg.id, decision_type="classify", model=meta.model,
            output=result.model_dump(), confidence=result.confidence,
            alternatives=[a.model_dump() for a in result.alternatives],
            guardrails={"schema_ok": True, "repaired": meta.repaired},
            tokens_in=meta.tokens_in, tokens_out=meta.tokens_out, latency_ms=meta.latency_ms,
            trace_id=agg.trace_id,
        ))
        used = agg.token_budget_used + meta.tokens_in + meta.tokens_out
        updates = {"classification": classification, "token_budget_used": used}
        agg2 = agg.model_copy(update=updates)
        await _commit(agg2, EventType.CLASSIFIED, line=result.line, peril=result.peril,
                      severity=result.severity, confidence=result.confidence)
        _check_budget(agg2)
        return updates

    async def investigate(agg: ClaimAggregate) -> dict[str, Any]:
        """Read-only (T0) tools gather routing inputs: policy, coverage (RAG-
        grounded), estimate, history, duplicates (exact + semantic), weather, and
        a fraud score. Tolerant of missing data; sets a degraded flag if a fraud
        control is down."""
        coverage = Coverage()
        policy_status = PolicyStatus.UNKNOWN
        policy_id = agg.policy_id
        amount_est = agg.financials.amount_est
        loss_date = agg.extraction.fields.get("loss_date", "")
        peril = agg.classification.peril or "other"
        degraded = get_settings().fraud_controls_degraded

        if agg.policy_number:
            pol = await deps.executor.execute(
                None, "policy_lookup", {"policy_number": agg.policy_number},
                claim_id=agg.id, trace_id=agg.trace_id)
            if pol.ok and pol.data:
                policy_id = pol.data["policy_id"]
                policy_status = PolicyStatus(pol.data["status"])
                cov = await deps.executor.execute(
                    None, "coverage_check",
                    {"policy_id": policy_id, "peril": peril, "loss_date": loss_date,
                     "fields": agg.extraction.fields},
                    claim_id=agg.id, trace_id=agg.trace_id)
                if cov.ok and cov.data:
                    coverage = Coverage.model_validate(cov.data)

        est = await deps.executor.execute(
            None, "repair_cost_estimator",
            {"line": peril, "damage_items": [{"part": peril}]},
            claim_id=agg.id, trace_id=agg.trace_id)
        if est.ok and est.data:
            amount_est = est.data["total"]

        # Weather corroboration for weather perils (mock NOAA).
        if peril in {"hail", "weather", "wind", "flood", "storm"}:
            wx = await deps.executor.execute(
                None, "weather_event_verify",
                {"peril": peril, "date": loss_date,
                 "location": agg.extraction.fields.get("loss_location", "")},
                claim_id=agg.id, trace_id=agg.trace_id)
            if wx.data and wx.data.get("degraded"):
                degraded = True

        # ── RAG-grounded coverage determination + citation enforcement (thesis 8)
        gs = await deps.executor.execute(
            None, "guideline_search",
            {"query": f"{peril} coverage policy status {policy_status.value}", "k": 5},
            claim_id=agg.id, trace_id=agg.trace_id)
        chunks = (gs.data or {}).get("chunks", [])
        if chunks and policy_id and deps.ground_coverage:
            det, meta = await determine_coverage(
                deps.planner,
                query=f"Is a {peril} loss covered under policy {policy_id} "
                      f"(status {policy_status.value}, loss {loss_date})?",
                chunks=chunks)
            grounded, guardrails = apply_citation_floor(det, {c["id"] for c in chunks})
            coverage = grounded
            await store.record_decision(DecisionRecord(
                claim_id=agg.id, decision_type="action", model=meta.model,
                output=det.model_dump(), confidence=grounded.confidence,
                citations=grounded.citations, guardrails=guardrails,
                tokens_in=meta.tokens_in, tokens_out=meta.tokens_out,
                latency_ms=meta.latency_ms, trace_id=agg.trace_id))
        elif chunks and coverage.covered is not None and not coverage.citations:
            # offline grounding: attach the top retrieved chunk as a citation chip
            coverage = coverage.model_copy(update={"citations": [chunks[0]["id"]]})

        # ── fraud: history → exact + semantic duplicate → rules scan
        history = await deps.executor.execute(
            None, "claim_history", {"claimant_id": agg.claimant_id or "unknown"},
            claim_id=agg.id, trace_id=agg.trace_id)
        h = history.data or {}
        dup = await deps.executor.execute(
            None, "duplicate_claim_check",
            {"claim_id": agg.id, "claimant_id": agg.claimant_id or "unknown",
             "peril": peril, "loss_date": loss_date, "narrative": agg.fnol_text},
            claim_id=agg.id, trace_id=agg.trace_id)
        exact = (dup.data or {}).get("exact_matches", [])
        semantic = (dup.data or {}).get("semantic_matches", [])
        if (dup.data or {}).get("degraded"):
            degraded = True
        narrative_sim = max((m["similarity"] for m in semantic), default=0.0)
        scan = await deps.executor.execute(
            None, "fraud_signal_scan",
            {"claim_id": agg.id, "prior_count_24m": h.get("count_24m", 0),
             "exact_duplicate": bool(exact), "narrative_similarity": narrative_sim,
             "first_seen": h.get("first_seen", False),
             "recent_coverage_increase": h.get("recent_coverage_increase", False)},
            claim_id=agg.id, trace_id=agg.trace_id)
        fraud_score = (scan.data or {}).get("score", 0.0)
        fraud_signals = (scan.data or {}).get("signals", [])

        fin = agg.financials.model_copy(update={"amount_est": amount_est})
        dup_refs = exact + [m["claim_id"] for m in semantic]
        updates = {
            "coverage": coverage, "policy_status": policy_status, "policy_id": policy_id,
            "financials": fin, "fraud_score": fraud_score, "fraud_signals": fraud_signals,
            "state": ClaimState.TRIAGE,
            "open_questions": [f"duplicate of {m}" for m in dup_refs],
            "duplicate_hard_match": bool(exact),
            "degraded": degraded,
        }
        await _commit(agg.model_copy(update=updates), EventType.INVESTIGATED,
                      covered=coverage.covered, amount_est=amount_est, fraud_score=fraud_score,
                      policy_status=policy_status.value, duplicates=dup_refs,
                      citations=coverage.citations, degraded=degraded)
        if degraded:
            await _commit(agg.model_copy(update=updates), EventType.DEGRADED_MODE,
                          reason="fraud_control_unavailable")
        return updates

    async def route_node(agg: ClaimAggregate) -> dict[str, Any]:
        required = agg.extraction.missing_required
        present_conf = [v for k, v in agg.extraction.field_confidence.items() if k not in required]
        inp = RouterInput(
            completeness=agg.extraction.completeness,
            min_field_confidence=min(present_conf) if present_conf else 1.0,
            policy_active=agg.policy_status == PolicyStatus.ACTIVE,
            coverage_covered=agg.coverage.covered,
            coverage_confidence=agg.coverage.confidence,
            clear_exclusion=bool(agg.coverage.exclusions_triggered),
            exclusion_confidence=agg.coverage.confidence if agg.coverage.exclusions_triggered else 0.0,
            fraud_score=agg.fraud_score,
            severity=agg.classification.severity or 3,
            amount_est=agg.financials.amount_est or 0.0,
            classification_confidence=agg.classification.confidence,
            injury_flag=agg.classification.injury_flag,
            attorney_flag=agg.classification.attorney_flag,
            duplicate_hard_match=agg.duplicate_hard_match,
        )
        decision = route(inp, deps.routing_config)
        await store.record_decision(DecisionRecord(
            claim_id=agg.id, decision_type="route", output=decision.model_dump(),
            rule_id=decision.rule_id, config_version=deps.config_version,
            guardrails={"needs_tiebreak": decision.needs_tiebreak}, trace_id=agg.trace_id,
        ))
        workflow = decision.workflow
        rule_id = decision.rule_id
        rationale = decision.rationale

        # R-06 ambiguous band: the ONLY place the LLM influences routing. flash,
        # grounded in fraud guidelines, chooses W2 or W3; logged with alternatives.
        if decision.needs_tiebreak and deps.ground_coverage:
            gs = await deps.executor.execute(
                None, "guideline_search", {"query": "fraud screening indicators", "k": 4},
                claim_id=agg.id, trace_id=agg.trace_id)
            tb, meta = await decide_tiebreak(
                deps.planner,
                context=f"fraud_score={agg.fraud_score}, signals={agg.fraud_signals}",
                chunks=(gs.data or {}).get("chunks", []))
            workflow = Workflow(tb.workflow)
            rule_id = "R-06"
            rationale = f"tiebreak -> {tb.workflow}: {tb.rationale}"
            await store.record_decision(DecisionRecord(
                claim_id=agg.id, decision_type="tiebreak", model=meta.model,
                output=tb.model_dump(), confidence=tb.confidence,
                alternatives=[a.model_dump() for a in tb.alternatives],
                tokens_in=meta.tokens_in, tokens_out=meta.tokens_out,
                latency_ms=meta.latency_ms, trace_id=agg.trace_id))

        # Degraded fraud control: never STP — cap W1 at W2 (thesis 7).
        if agg.degraded and workflow == Workflow.W1:
            workflow = Workflow.W2
            rule_id = "R-DEGRADED"
            rationale = "fraud control degraded -> cap at W2 (no straight-through)"

        updates = {
            "workflow": workflow, "rule_id": rule_id,
            "config_version": deps.config_version, "state": ClaimState.PLANNING,
        }
        await _commit(agg.model_copy(update=updates), EventType.ROUTED,
                      workflow=workflow.value, rule_id=rule_id, rationale=rationale)
        return updates

    # ── W1 straight-through ────────────────────────────────────────────────────
    async def w1_execute(agg: ClaimAggregate) -> dict[str, Any]:
        ceiling = deps.routing_config.auto_pay_ceiling
        amount = agg.financials.amount_est or 0.0
        await _commit(agg.model_copy(update={"state": ClaimState.EXECUTING}),
                      EventType.EXECUTING, plan=["reserve_set", "payment_execute", "customer_comm_send"])
        await deps.executor.execute(Workflow.W1, "reserve_set",
            {"claim_id": agg.id, "amount": amount, "rationale": "STP repair estimate",
             "idempotency_key": f"{agg.id}-rsv-1"}, claim_id=agg.id, trace_id=agg.trace_id)
        gate = PaymentAuthorization(policy_gate_ref=f"W1-T0-ceiling-{int(ceiling)}")
        pay = await deps.executor.execute(Workflow.W1, "payment_execute",
            {"claim_id": agg.id, "payee_id": agg.claimant_id or "payee", "amount": amount,
             "method": "ACH", "authorization": gate, "idempotency_key": f"{agg.id}-pay-1"},
            claim_id=agg.id, trace_id=agg.trace_id)
        await deps.executor.execute(Workflow.W1, "customer_comm_send",
            {"claim_id": agg.id, "template_id": "settlement_paid", "mode": "draft",
             "merge_fields": {"holder": agg.claimant_id or "claimant", "amount": amount, "method": "ACH"}},
            claim_id=agg.id, trace_id=agg.trace_id)
        paid = amount if pay.ok else 0.0
        fin = agg.financials.model_copy(update={"reserve": amount, "paid": paid})
        # The financials are persisted together with the SETTLED event in the
        # settle node (thesis 5: no projection write without its event).
        return {"financials": fin, "state": ClaimState.EXECUTING}

    async def settle(agg: ClaimAggregate) -> dict[str, Any]:
        updates = {"state": ClaimState.SETTLEMENT}
        await _commit(agg.model_copy(update=updates), EventType.SETTLED, paid=agg.financials.paid)
        return updates

    async def close(agg: ClaimAggregate) -> dict[str, Any]:
        updates = {"state": ClaimState.CLOSED}
        await _commit(agg.model_copy(update=updates), EventType.CLOSED)
        return updates

    # ── W2 standard adjudication (human approval via interrupt) ────────────────
    async def w2_propose(agg: ClaimAggregate) -> dict[str, Any]:
        appr_id = f"appr_{agg.id}"
        deny = agg.coverage.covered is False or agg.rule_id == "R-02"
        updates: dict[str, Any] = {"state": ClaimState.REVIEW_PENDING}
        action: dict[str, Any]
        if deny:
            letter, meta = await draft_letter(
                deps.planner, claim_id=agg.id, kind="claim denial",
                context=agg.coverage.rationale or "Policy not in force on the loss date.")
            await deps.executor.execute(Workflow.W2, "customer_comm_send",
                {"claim_id": agg.id, "template_id": "free_text", "mode": "draft",
                 "merge_fields": {"body": letter.body}}, claim_id=agg.id, trace_id=agg.trace_id)
            action = {"type": "deny", "reason": agg.coverage.rationale,
                      "letter_subject": letter.subject, "letter_body": letter.body}
            updates["token_budget_used"] = agg.token_budget_used + meta.tokens_in + meta.tokens_out
        else:
            amount = agg.financials.amount_est or 0.0
            await deps.executor.execute(Workflow.W2, "reserve_set",
                {"claim_id": agg.id, "amount": amount, "rationale": "W2 proposed payout",
                 "idempotency_key": f"{agg.id}-rsv-1"}, claim_id=agg.id, trace_id=agg.trace_id)
            updates["financials"] = agg.financials.model_copy(update={"reserve": amount})
            action = {"type": "pay", "amount": amount, "payee_id": agg.claimant_id}

        await store.create_approval(ApprovalRecord(
            id=appr_id, claim_id=agg.id, requested_action=action, risk_tier=2,
            confidence=agg.confidence, evidence_refs=[s.get("code") for s in agg.fraud_signals],
            sla_at=None,
        ))
        agg2 = agg.model_copy(update=updates)
        await _commit(agg2, EventType.APPROVAL_REQUESTED, approval_id=appr_id, action=action)
        _check_budget(agg2)  # the deny path drafts a letter (flash) → account for it
        return updates

    async def w2_await(agg: ClaimAggregate) -> dict[str, Any]:
        appr_id = f"appr_{agg.id}"
        # interrupt() pauses here; the checkpointer persists state. The resolve
        # endpoint resumes with Command(resume={resolution, delta, ...}).
        resume: dict[str, Any] = interrupt({"approval_id": appr_id, "claim_id": agg.id})
        resolution = resume.get("resolution", "approve")
        delta = resume.get("delta")
        await store.resolve_approval(
            appr_id, resolution=resolution, delta=delta,
            reason_code=resume.get("reason_code"), resolved_by=resume.get("resolved_by"))
        appr = await store.get_approval(appr_id) or {}
        action = appr.get("requested_action", {})

        if resolution == "reject":
            await deps.executor.execute(Workflow.W2, "escalate_to_human",
                {"claim_id": agg.id, "reason_code": "REJECTED", "risk_tier": 2,
                 "summary": "Approver rejected the agent's proposal"},
                claim_id=agg.id, trace_id=agg.trace_id)
            updates: dict[str, Any] = {"state": ClaimState.ESCALATED,
                                       "reason_code": "APPROVAL_REJECTED"}
            await _commit(agg.model_copy(update=updates), EventType.APPROVAL_RESOLVED,
                          resolution=resolution)
            return updates

        if action.get("type") == "deny":
            auth = PaymentAuthorization(approval_ref=appr_id)  # gate the T2 send
            await deps.executor.execute(Workflow.W2, "customer_comm_send",
                {"claim_id": agg.id, "template_id": "free_text", "mode": "send",
                 "authorization": auth, "merge_fields": {"body": action.get("letter_body", "")}},
                claim_id=agg.id, trace_id=agg.trace_id)
            updates = {"state": ClaimState.DENIED, "reason_code": "DENIED_AFTER_REVIEW"}
            await _commit(agg.model_copy(update=updates), EventType.APPROVAL_RESOLVED,
                          resolution=resolution)
            await _commit(agg.model_copy(update=updates), EventType.DENIED,
                          reason=action.get("reason"))
            return updates

        # pay (approve or modify)
        amount = float(
            (delta or {}).get("amount", action.get("amount", 0.0))
            if resolution == "modify" else action.get("amount", 0.0)
        )
        auth = PaymentAuthorization(approval_ref=appr_id)
        pay = await deps.executor.execute(Workflow.W2, "payment_execute",
            {"claim_id": agg.id, "payee_id": agg.claimant_id or "payee", "amount": amount,
             "method": "ACH", "authorization": auth, "idempotency_key": f"{agg.id}-pay-1"},
            claim_id=agg.id, trace_id=agg.trace_id)
        fin = agg.financials.model_copy(
            update={"reserve": max(agg.financials.reserve, amount), "paid": amount if pay.ok else 0.0})
        updates = {"state": ClaimState.SETTLEMENT, "financials": fin}
        await _commit(agg.model_copy(update=updates), EventType.APPROVAL_RESOLVED,
                      resolution=resolution, amount=amount)
        await _commit(agg.model_copy(update=updates), EventType.SETTLED, paid=fin.paid)
        return updates

    # ── W3 fraud (SIU) — no payment edge ───────────────────────────────────────
    async def w3_fraud(agg: ClaimAggregate) -> dict[str, Any]:
        await deps.executor.execute(Workflow.W3, "escalate_to_human",
            {"claim_id": agg.id, "reason_code": "W3", "risk_tier": 2,
             "summary": "Fraud signals exceeded threshold; routed to SIU",
             "evidence_refs": [s.get("code") for s in agg.fraud_signals]},
            claim_id=agg.id, trace_id=agg.trace_id)
        updates = {"state": ClaimState.ESCALATED, "reason_code": "FRAUD_SIU"}
        await _commit(agg.model_copy(update=updates), EventType.ESCALATED, queue="siu",
                      fraud_score=agg.fraud_score, signals=agg.fraud_signals)
        return updates

    # ── W5 high-severity escalation ────────────────────────────────────────────
    async def w5_escalate(agg: ClaimAggregate) -> dict[str, Any]:
        await deps.executor.execute(Workflow.W5, "escalate_to_human",
            {"claim_id": agg.id, "reason_code": "W5", "risk_tier": 2,
             "summary": "High-severity claim prepared for a senior adjuster",
             "evidence_refs": []}, claim_id=agg.id, trace_id=agg.trace_id)
        updates = {"state": ClaimState.ESCALATED, "reason_code": "HIGH_SEVERITY"}
        await _commit(agg.model_copy(update=updates), EventType.ESCALATED, queue="senior_adjuster")
        return updates

    # ── W4 information request loop ────────────────────────────────────────────
    async def w4_request(agg: ClaimAggregate) -> dict[str, Any]:
        doc_types = agg.extraction.missing_required or ["police_report"]
        await deps.executor.execute(Workflow.W4, "document_request_create",
            {"claim_id": agg.id, "doc_types": doc_types, "due_days": 14},
            claim_id=agg.id, trace_id=agg.trace_id)
        updates = {"state": ClaimState.INFO_PENDING}
        await _commit(agg.model_copy(update=updates), EventType.PARKED, state="INFO_PENDING",
                      workflow="W4", reason="awaiting_documents", doc_types=doc_types)
        return updates

    async def w4_await(agg: ClaimAggregate) -> dict[str, Any]:
        resume: dict[str, Any] = interrupt(
            {"claim_id": agg.id, "awaiting": agg.extraction.missing_required})
        provided = resume.get("fields", {})
        replans = agg.replan_count + 1
        if replans > settings.max_replans:
            updates = {"state": ClaimState.ESCALATED, "reason_code": "REPLAN_LIMIT",
                       "replan_count": replans}
            await _commit(agg.model_copy(update=updates), EventType.REPLAN_LIMIT, count=replans)
            return updates
        new_fields = {**agg.extraction.fields, **provided}
        extraction = Extraction(
            fields=new_fields,
            field_confidence={**agg.extraction.field_confidence, **{k: 0.95 for k in provided}},
            missing_required=[], completeness=1.0,
        )
        updates = {
            "extraction": extraction, "replan_count": replans, "state": ClaimState.TRIAGE,
            "policy_number": provided.get("policy_number") or agg.policy_number,
        }
        await _commit(agg.model_copy(update=updates), EventType.DOCUMENT_RECEIVED,
                      provided=list(provided.keys()), replan=replans)
        return updates

    # ── routing edges ──────────────────────────────────────────────────────────
    def after_route(agg: ClaimAggregate) -> str:
        return {
            Workflow.W1: "w1_execute", Workflow.W2: "w2_propose", Workflow.W3: "w3_fraud",
            Workflow.W4: "w4_request", Workflow.W5: "w5_escalate",
        }.get(agg.workflow or Workflow.W2, "w2_propose")

    def after_w2(agg: ClaimAggregate) -> str:
        return "close" if agg.state == ClaimState.SETTLEMENT else END

    def after_w4(agg: ClaimAggregate) -> str:
        return "investigate" if agg.state == ClaimState.TRIAGE else END

    g: Any = StateGraph(ClaimAggregate)
    for name, fn in [
        ("intake", intake), ("extract", extract), ("classify", classify),
        ("investigate", investigate), ("route", route_node), ("w1_execute", w1_execute),
        ("settle", settle), ("close", close), ("w2_propose", w2_propose), ("w2_await", w2_await),
        ("w3_fraud", w3_fraud), ("w5_escalate", w5_escalate), ("w4_request", w4_request),
        ("w4_await", w4_await),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "intake")
    g.add_edge("intake", "extract")
    g.add_edge("extract", "classify")
    g.add_edge("classify", "investigate")
    g.add_edge("investigate", "route")
    g.add_conditional_edges("route", after_route, {
        "w1_execute": "w1_execute", "w2_propose": "w2_propose", "w3_fraud": "w3_fraud",
        "w4_request": "w4_request", "w5_escalate": "w5_escalate",
    })
    g.add_edge("w1_execute", "settle")
    g.add_edge("settle", "close")
    g.add_edge("close", END)
    g.add_edge("w2_propose", "w2_await")
    g.add_conditional_edges("w2_await", after_w2, {"close": "close", END: END})
    g.add_edge("w3_fraud", END)
    g.add_edge("w5_escalate", END)
    g.add_edge("w4_request", "w4_await")
    g.add_conditional_edges("w4_await", after_w4, {"investigate": "investigate", END: END})
    return g


async def run_claim(
    agg: ClaimAggregate,
    deps: LifecycleDeps,
    *,
    checkpointer: Any | None = None,
    thread_id: str | None = None,
) -> ClaimAggregate:
    """Compile + run the lifecycle for one claim. Returns the aggregate at the
    first interrupt (REVIEW_PENDING / INFO_PENDING) or at a terminal state.
    Catches EscalateToHuman → ESCALATED."""
    if agg.trace_id is None:
        agg = agg.model_copy(update={"trace_id": f"trc_{uuid.uuid4().hex[:10]}"})
    app: Any = build_lifecycle_graph(deps).compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id or agg.id}}
    try:
        final = await app.ainvoke(agg, config)
        return ClaimAggregate.model_validate(final)
    except EscalateToHuman as exc:
        return await _record_escalation(agg, deps, exc)


async def resume_claim(
    deps: LifecycleDeps,
    *,
    checkpointer: Any,
    thread_id: str,
    resume_value: dict[str, Any],
) -> ClaimAggregate:
    """Resume a paused claim (interrupt) with Command(resume=...). The graph
    continues from inside w2_await / w4_await. Works across process restarts when
    the checkpointer is the shared Postgres saver."""
    app: Any = build_lifecycle_graph(deps).compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        final = await app.ainvoke(Command(resume=resume_value), config)
        return ClaimAggregate.model_validate(final)
    except EscalateToHuman as exc:
        # Reconstruct a minimal aggregate id from the thread for the escalation row.
        snapshot = await app.aget_state(config)
        agg = ClaimAggregate.model_validate(snapshot.values)
        return await _record_escalation(agg, deps, exc)


async def _record_escalation(
    agg: ClaimAggregate, deps: LifecycleDeps, exc: EscalateToHuman
) -> ClaimAggregate:
    escalated = agg.model_copy(
        update={"state": ClaimState.ESCALATED, "reason_code": exc.reason_code})
    await deps.store.commit_transition(
        escalated,
        claim_event(agg.id, EventType.ESCALATED, component="executor",
                    data={"reason": exc.reason_code, "message": exc.message},
                    trace_id=agg.trace_id),
    )
    return escalated

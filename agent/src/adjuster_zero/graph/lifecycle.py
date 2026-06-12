"""The claim lifecycle as a LangGraph StateGraph — the agent's spine (thesis 1).

Nodes: intake → extract → classify → investigate → route → {w1_execute | park}
→ settle → close. The LLM proposes (extract/classify); the graph disposes
(routes, gates, executes). Every node emits a typed claim_events row via the
injected store (thesis 5). Bounded autonomy (thesis 6) is enforced by a token
budget check that raises EscalateToHuman, caught by run_claim.

State schema = the ClaimAggregate itself (serializable → checkpointable). Deps
(store, planner client, tool executor) live in closures, not in checkpointed
state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

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
from ..persistence.store import ClaimStore, DecisionRecord
from ..planner import classify_claim, extract_fnol_fields
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

    async def intake(agg: ClaimAggregate) -> dict[str, Any]:
        agg2 = agg.model_copy(update={"state": ClaimState.RECEIVED})
        await _commit(agg2, EventType.RECEIVED, fnol_chars=len(agg.fnol_text))
        return {"state": ClaimState.RECEIVED}

    async def extract(agg: ClaimAggregate) -> dict[str, Any]:
        result, meta = await extract_fnol_fields(deps.planner, agg.fnol_text)
        fields = {f.name: f.value for f in result.fields if f.value is not None}
        field_conf = {f.name: f.confidence for f in result.fields}
        extraction = Extraction(
            fields=fields,
            field_confidence=field_conf,
            missing_required=result.missing_required,
            completeness=result.overall_completeness,
        )
        await store.record_decision(
            DecisionRecord(
                claim_id=agg.id,
                decision_type="extract",
                model=meta.model,
                output=result.model_dump(),
                confidence=result.overall_completeness,
                guardrails={"schema_ok": True, "repaired": meta.repaired},
                tokens_in=meta.tokens_in,
                tokens_out=meta.tokens_out,
                latency_ms=meta.latency_ms,
                trace_id=agg.trace_id,
            )
        )
        used = agg.token_budget_used + meta.tokens_in + meta.tokens_out
        updates: dict[str, Any] = {
            "extraction": extraction,
            "token_budget_used": used,
            "state": ClaimState.TRIAGE,
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
            line=result.line,
            peril=result.peril,
            severity=result.severity,
            complexity=result.complexity,
            injury_flag=result.injury_flag,
            attorney_flag=result.attorney_flag,
            confidence=result.confidence,
            alternatives=[ClassAlternative(label=a.label, p=a.p) for a in result.alternatives],
        )
        await store.record_decision(
            DecisionRecord(
                claim_id=agg.id,
                decision_type="classify",
                model=meta.model,
                output=result.model_dump(),
                confidence=result.confidence,
                alternatives=[a.model_dump() for a in result.alternatives],
                guardrails={"schema_ok": True, "repaired": meta.repaired},
                tokens_in=meta.tokens_in,
                tokens_out=meta.tokens_out,
                latency_ms=meta.latency_ms,
                trace_id=agg.trace_id,
            )
        )
        used = agg.token_budget_used + meta.tokens_in + meta.tokens_out
        updates = {"classification": classification, "token_budget_used": used}
        agg2 = agg.model_copy(update=updates)
        await _commit(agg2, EventType.CLASSIFIED, line=result.line, peril=result.peril,
                      severity=result.severity, confidence=result.confidence)
        _check_budget(agg2)
        return updates

    async def investigate(agg: ClaimAggregate) -> dict[str, Any]:
        """Run read-only (T0) tools to gather routing inputs. Tolerant of missing
        data (e.g. no policy number → skip lookup); failures are recorded, not fatal."""
        updates: dict[str, Any] = {}
        coverage = Coverage()
        policy_status = PolicyStatus.UNKNOWN
        policy_id = agg.policy_id
        amount_est = agg.financials.amount_est

        if agg.policy_number:
            pol = await deps.executor.execute(
                None, "policy_lookup", {"policy_number": agg.policy_number},
                claim_id=agg.id, trace_id=agg.trace_id,
            )
            if pol.ok and pol.data:
                policy_id = pol.data["policy_id"]
                policy_status = PolicyStatus(pol.data["status"])
                cov = await deps.executor.execute(
                    None, "coverage_check",
                    {
                        "policy_id": policy_id,
                        "peril": agg.classification.peril or "other",
                        "loss_date": agg.extraction.fields.get("loss_date", ""),
                        "fields": agg.extraction.fields,
                    },
                    claim_id=agg.id, trace_id=agg.trace_id,
                )
                if cov.ok and cov.data:
                    coverage = Coverage.model_validate(cov.data)

        est = await deps.executor.execute(
            None, "repair_cost_estimator",
            {"line": agg.classification.peril or "other",
             "damage_items": [{"part": agg.classification.peril or "other"}]},
            claim_id=agg.id, trace_id=agg.trace_id,
        )
        if est.ok and est.data:
            amount_est = est.data["total"]

        fin = agg.financials.model_copy(update={"amount_est": amount_est})
        updates = {
            "coverage": coverage,
            "policy_status": policy_status,
            "policy_id": policy_id,
            "financials": fin,
            "state": ClaimState.TRIAGE,
        }
        await _commit(agg.model_copy(update=updates), EventType.INVESTIGATED,
                      covered=coverage.covered, amount_est=amount_est,
                      policy_status=policy_status.value)
        return updates

    async def route_node(agg: ClaimAggregate) -> dict[str, Any]:
        required = agg.extraction.missing_required
        present_conf = [
            v for k, v in agg.extraction.field_confidence.items() if k not in required
        ]
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
        )
        decision = route(inp, deps.routing_config)
        await store.record_decision(
            DecisionRecord(
                claim_id=agg.id,
                decision_type="route",
                output=decision.model_dump(),
                rule_id=decision.rule_id,
                config_version=deps.config_version,
                trace_id=agg.trace_id,
            )
        )
        updates = {
            "workflow": decision.workflow,
            "rule_id": decision.rule_id,
            "config_version": deps.config_version,
            "state": ClaimState.PLANNING,
        }
        await _commit(agg.model_copy(update=updates), EventType.ROUTED,
                      workflow=decision.workflow.value, rule_id=decision.rule_id,
                      rationale=decision.rationale)
        return updates

    async def w1_execute(agg: ClaimAggregate) -> dict[str, Any]:
        ceiling = deps.routing_config.auto_pay_ceiling
        amount = agg.financials.amount_est or 0.0
        await _commit(
            agg.model_copy(update={"state": ClaimState.EXECUTING}),
            EventType.EXECUTING,
            plan=["reserve_set", "payment_execute", "customer_comm_send"],
        )
        # reserve
        await deps.executor.execute(
            Workflow.W1, "reserve_set",
            {"claim_id": agg.id, "amount": amount, "rationale": "STP glass repair estimate",
             "idempotency_key": f"{agg.id}-rsv-1"},
            claim_id=agg.id, trace_id=agg.trace_id,
        )
        # payment — gate ref is the tier-0 policy ceiling (structural, required)
        gate = PaymentAuthorization(policy_gate_ref=f"W1-T0-ceiling-{int(ceiling)}")
        pay = await deps.executor.execute(
            Workflow.W1, "payment_execute",
            {"claim_id": agg.id, "payee_id": agg.claimant_id or "payee",
             "amount": amount, "method": "ACH", "authorization": gate,
             "idempotency_key": f"{agg.id}-pay-1"},
            claim_id=agg.id, trace_id=agg.trace_id,
        )
        # settlement letter (draft)
        await deps.executor.execute(
            Workflow.W1, "customer_comm_send",
            {"claim_id": agg.id, "template_id": "settlement_paid", "mode": "draft",
             "merge_fields": {"holder": agg.claimant_id or "claimant",
                              "amount": amount, "method": "ACH"}},
            claim_id=agg.id, trace_id=agg.trace_id,
        )
        paid = amount if pay.ok else 0.0
        fin = agg.financials.model_copy(update={"reserve": amount, "paid": paid})
        # Mid-EXECUTING financial accrual is not a state transition, so the
        # projection update needs no event row.
        updates = {"financials": fin, "state": ClaimState.EXECUTING}
        await store.upsert_claim(agg.model_copy(update=updates))
        return updates

    async def settle(agg: ClaimAggregate) -> dict[str, Any]:
        updates = {"state": ClaimState.SETTLEMENT}
        await _commit(agg.model_copy(update=updates), EventType.SETTLED, paid=agg.financials.paid)
        return updates

    async def close(agg: ClaimAggregate) -> dict[str, Any]:
        updates = {"state": ClaimState.CLOSED}
        await _commit(agg.model_copy(update=updates), EventType.CLOSED)
        return updates

    async def park(agg: ClaimAggregate) -> dict[str, Any]:
        # W4 → INFO_PENDING (awaiting documents); everything else → REVIEW_PENDING.
        new_state = ClaimState.INFO_PENDING if agg.workflow == Workflow.W4 else ClaimState.REVIEW_PENDING
        reason = "awaiting_documents" if agg.workflow == Workflow.W4 else "human_review_required"
        updates = {"state": new_state, "reason_code": reason}
        await _commit(
            agg.model_copy(update=updates), EventType.PARKED, state=new_state.value,
            workflow=agg.workflow.value if agg.workflow else None, reason=reason,
        )
        return updates

    def after_route(agg: ClaimAggregate) -> str:
        return "w1_execute" if agg.workflow == Workflow.W1 else "park"

    # LangGraph's add_node/ainvoke overloads don't model Pydantic-state + dict
    # partial updates cleanly; typing the builder as Any avoids spurious errors
    # (graph wiring is runtime-validated by LangGraph and covered by tests).
    g: Any = StateGraph(ClaimAggregate)
    g.add_node("intake", intake)
    g.add_node("extract", extract)
    g.add_node("classify", classify)
    g.add_node("investigate", investigate)
    g.add_node("route", route_node)
    g.add_node("w1_execute", w1_execute)
    g.add_node("settle", settle)
    g.add_node("close", close)
    g.add_node("park", park)

    g.add_edge(START, "intake")
    g.add_edge("intake", "extract")
    g.add_edge("extract", "classify")
    g.add_edge("classify", "investigate")
    g.add_edge("investigate", "route")
    g.add_conditional_edges("route", after_route, {"w1_execute": "w1_execute", "park": "park"})
    g.add_edge("w1_execute", "settle")
    g.add_edge("settle", "close")
    g.add_edge("close", END)
    g.add_edge("park", END)
    return g


async def run_claim(
    agg: ClaimAggregate,
    deps: LifecycleDeps,
    *,
    checkpointer: Any | None = None,
    thread_id: str | None = None,
) -> ClaimAggregate:
    """Compile + run the lifecycle for one claim. Catches EscalateToHuman (budget
    exhaustion, schema-repair failure, disallowed tool) and records ESCALATED."""
    if agg.trace_id is None:
        agg = agg.model_copy(update={"trace_id": f"trc_{uuid.uuid4().hex[:10]}"})
    app: Any = build_lifecycle_graph(deps).compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id or agg.id}}
    try:
        final = await app.ainvoke(agg, config)
        return ClaimAggregate.model_validate(final)
    except EscalateToHuman as exc:
        escalated = agg.model_copy(
            update={"state": ClaimState.ESCALATED, "reason_code": exc.reason_code}
        )
        await deps.store.commit_transition(
            escalated,
            claim_event(agg.id, EventType.ESCALATED, component="executor",
                        data={"reason": exc.reason_code, "message": exc.message},
                        trace_id=agg.trace_id),
        )
        return escalated

"""Mock tool handlers (Phase 1). Deterministic, synthetic, no external calls.

These stand in for the policy-admin system, a rules-only coverage engine, a
parts/labor estimator, the reserve ledger, a mock ACH rail, and a comms
templater. Real RAG-grounded coverage and fraud scans arrive in Phase 3.
"""

from __future__ import annotations

import datetime as dt

from ..seed.data import CLAIM_HISTORY, POLICIES, RECENT_COVERAGE_INCREASE
from .base import ToolFailure
from .schemas import (
    ClaimHistoryArgs,
    ClaimHistoryResult,
    CommSendArgs,
    CommSendResult,
    CoverageCheckArgs,
    CoverageCheckResult,
    DocRequestArgs,
    DocRequestResult,
    DuplicateCheckArgs,
    DuplicateCheckResult,
    EscalateArgs,
    EscalateResult,
    FraudScanArgs,
    FraudScanResult,
    FraudSignal,
    PaymentExecuteArgs,
    PaymentExecuteResult,
    PolicyLookupArgs,
    PolicyLookupResult,
    PriorClaim,
    RepairCostArgs,
    RepairCostResult,
    RepairLineItem,
    ReserveSetArgs,
    ReserveSetResult,
    WeatherEvent,
    WeatherVerifyArgs,
    WeatherVerifyResult,
)

# peril → the coverage code that would apply
_PERIL_COVERAGE = {
    "glass": "AUTO-COMP",
    "hail": "AUTO-COMP",
    "theft": "AUTO-COMP",
    "weather": "AUTO-COMP",
    "collision": "AUTO-COLL",
}

# crude parts/labor table for the estimator mock
_PERIL_ESTIMATE = {
    "glass": (RepairLineItem(desc="Windshield (OEM)", parts=320, labor_hours=1.2, rate=76, total=411.2), 0.93),
    "collision": (RepairLineItem(desc="Front bumper + fender", parts=1900, labor_hours=10, rate=90, total=2800), 0.82),
    "hail": (RepairLineItem(desc="PDR multi-panel", parts=400, labor_hours=16, rate=95, total=1920), 0.8),
}


async def policy_lookup(args: PolicyLookupArgs) -> PolicyLookupResult:
    rec = POLICIES.get(args.policy_number)
    if rec is None:
        raise ToolFailure("POLICY_NOT_FOUND", f"No policy {args.policy_number}", retryable=False)
    return PolicyLookupResult(**rec)


def _active_at(rec: dict, loss_date: str) -> bool:
    if rec["status"] != "active":
        # lapsed/cancelled: still check the effective window for a precise reason
        pass
    if not loss_date:
        return rec["status"] == "active"
    try:
        loss = dt.date.fromisoformat(loss_date)
        eff_from = dt.date.fromisoformat(rec["effective_from"])
        eff_to = dt.date.fromisoformat(rec["effective_to"])
    except ValueError:
        return rec["status"] == "active"
    return rec["status"] == "active" and eff_from <= loss <= eff_to


async def coverage_check(args: CoverageCheckArgs) -> CoverageCheckResult:
    rec = next((r for r in POLICIES.values() if r["policy_id"] == args.policy_id), None)
    if rec is None:
        raise ToolFailure("POLICY_NOT_FOUND", f"No policy id {args.policy_id}")

    active = _active_at(rec, args.loss_date)
    if not active:
        return CoverageCheckResult(
            covered=False,
            confidence=0.92,
            applicable_coverage=None,
            exclusions_triggered=["POLICY_INACTIVE"],
            rationale=(
                f"Policy {rec['policy_id']} status '{rec['status']}', effective through "
                f"{rec['effective_to']}; loss date {args.loss_date} is outside coverage."
            ),
        )

    needed = _PERIL_COVERAGE.get(args.peril)
    has = next((c for c in rec["coverages"] if c["code"] == needed), None)
    if needed and has:
        return CoverageCheckResult(
            covered=True,
            confidence=0.94,
            applicable_coverage=needed,
            rationale=f"Peril '{args.peril}' falls under {needed}; policy active at loss date.",
        )
    return CoverageCheckResult(
        covered=False,
        confidence=0.7,
        rationale=f"No coverage code matches peril '{args.peril}'.",
    )


async def repair_cost_estimator(args: RepairCostArgs) -> RepairCostResult:
    # Use the peril implied by the first damage item, else the line.
    key = args.damage_items[0].part if args.damage_items else args.line
    item, conf = _PERIL_ESTIMATE.get(key, (
        RepairLineItem(desc="General repair", parts=900, labor_hours=6, rate=85, total=1410),
        0.7,
    ))
    return RepairCostResult(line_items=[item], total=item.total, confidence=conf)


async def reserve_set(args: ReserveSetArgs) -> ReserveSetResult:
    # Mock ledger: the previous amount is unknown here (the executor's idempotency
    # store handles exactly-once); we just record the new reserve.
    return ReserveSetResult(
        reserve_id=f"rsv_{args.idempotency_key}", previous_amount=0.0, new_amount=args.amount
    )


async def payment_execute(args: PaymentExecuteArgs) -> PaymentExecuteResult:
    # args.authorization is REQUIRED by the schema; reaching here means a gate or
    # approval ref exists. Mock ACH always settles deterministically.
    return PaymentExecuteResult(
        payment_id=f"pay_{args.idempotency_key}",
        status="settled",
        settled_at="2026-06-12T00:00:00Z",
    )


_TEMPLATES = {
    "settlement_paid": "Dear {holder}, your claim {claim_id} has been settled. "
    "A payment of ${amount} via {method} is on its way. Thank you.",
    "denial_lapsed": "Dear {holder}, we reviewed claim {claim_id}. Coverage was not in "
    "force on the loss date, so we are unable to pay this claim. {rationale}",
    "info_request": "Dear claimant, to proceed with claim {claim_id} we need: {doc_types}.",
    # free_text renders an LLM-drafted body verbatim (used for flash-drafted letters).
    "free_text": "{body}",
}


async def customer_comm_send(args: CommSendArgs) -> CommSendResult:
    template = _TEMPLATES.get(args.template_id)
    if template is None:
        raise ToolFailure("TEMPLATE_NOT_FOUND", f"No template {args.template_id}")
    try:
        preview = template.format(**{"claim_id": args.claim_id, **args.merge_fields})
    except KeyError as exc:
        raise ToolFailure(
            "TEMPLATE_INCOMPLETE", f"Missing merge field {exc}", retryable=False
        ) from exc
    draft_id = f"draft_{args.claim_id}_{args.template_id}"
    if args.mode == "send":
        # 'send' writes to the comms thread + console; no real email (cut list).
        return CommSendResult(
            draft_id=draft_id, message_id=f"msg_{draft_id}", rendered_preview=preview, sent=True
        )
    return CommSendResult(draft_id=draft_id, rendered_preview=preview, sent=False)


def _within_24m(date: str, loss_date: str) -> bool:
    try:
        d = dt.date.fromisoformat(date)
        ref = dt.date.fromisoformat(loss_date) if loss_date else dt.date(2026, 6, 12)
    except ValueError:
        return True
    return (ref - d).days <= 730


async def claim_history(args: ClaimHistoryArgs) -> ClaimHistoryResult:
    history = CLAIM_HISTORY.get(args.claimant_id, [])
    priors = [
        PriorClaim(claim_id=h["claim_id"], date=h["date"], peril=h["peril"], paid=h["paid"])
        for h in history
    ]
    return ClaimHistoryResult(
        prior_claims=priors,
        count_24m=len(priors),
        first_seen=len(priors) == 0,
        recent_coverage_increase=args.claimant_id in RECENT_COVERAGE_INCREASE,
    )


async def duplicate_claim_check(args: DuplicateCheckArgs) -> DuplicateCheckResult:
    # Phase 2: exact-match only (same claimant + same peril + within date window).
    # Semantic (narrative embedding) matching arrives in Phase 3.
    history = CLAIM_HISTORY.get(args.claimant_id, [])
    exact = [
        h["claim_id"]
        for h in history
        if args.peril and h["peril"] == args.peril and _within_24m(h["date"], args.loss_date)
    ]
    return DuplicateCheckResult(exact_matches=exact)


async def fraud_signal_scan(args: FraudScanArgs) -> FraudScanResult:
    # Rules-only v1: weighted, itemized signals with evidence (Part 4 T-05).
    signals: list[FraudSignal] = []
    if args.exact_duplicate:
        signals.append(FraudSignal(code="DUP_EXACT", weight=0.35, evidence="exact duplicate claim found"))
    if args.narrative_similarity >= 0.85:
        signals.append(FraudSignal(
            code="DUP_NARRATIVE", weight=0.35,
            evidence=f"narrative cosine {args.narrative_similarity:.2f}"))
    if args.recent_coverage_increase:
        signals.append(FraudSignal(code="RECENT_COVERAGE_INCREASE", weight=0.20,
                                   evidence="coverage limit raised shortly before loss"))
    if args.prior_count_24m >= 3:
        signals.append(FraudSignal(code="FREQUENT_CLAIMS", weight=0.20,
                                   evidence=f"{args.prior_count_24m} claims in 24 months"))
    if args.first_seen:
        signals.append(FraudSignal(code="FIRST_SEEN", weight=0.05, evidence="no prior history"))
    score = min(1.0, round(sum(s.weight for s in signals), 2))
    return FraudScanResult(score=score, signals=signals)


async def document_request_create(args: DocRequestArgs) -> DocRequestResult:
    return DocRequestResult(
        request_id=f"docreq_{args.claim_id}",
        portal_url=f"https://portal.example/claims/{args.claim_id}/upload",
        expires_at="2026-06-26T00:00:00Z",
    )


async def escalate_to_human(args: EscalateArgs) -> EscalateResult:
    queue = {"W3": "siu", "W5": "senior_adjuster"}.get(args.reason_code, "ops")
    return EscalateResult(task_id=f"task_{args.claim_id}", queue=queue, sla_at="2026-06-13T00:00:00Z")


_WEATHER_PERILS = {"hail", "weather", "wind", "flood", "storm"}


async def weather_event_verify(args: WeatherVerifyArgs) -> WeatherVerifyResult:
    # Mock NOAA: corroborate weather perils. `verified: false` is a finding, not
    # an error (it feeds the fraud screen as PERIL_UNCORROBORATED).
    if args.peril.lower() in _WEATHER_PERILS:
        return WeatherVerifyResult(
            verified=True,
            event=WeatherEvent(type=args.peril.lower(), magnitude="1.75in", distance_km=3.1),
        )
    return WeatherVerifyResult(verified=False)

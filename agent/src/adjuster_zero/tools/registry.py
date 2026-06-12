"""Builds the tool registry: name → Tool (schemas, risk tier, idempotent, handler).

Tools that need the RAG layer (guideline_search) or embeddings (semantic
duplicate detection) receive them via an optional RagContext; without it they
degrade gracefully (empty retrieval / exact-match-only).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..rag.embed import Embedder, cosine
from ..rag.index import GuidelineIndex
from . import handlers
from .base import RiskTier, Tool
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
    GuidelineChunkOut,
    GuidelineSearchArgs,
    GuidelineSearchResult,
    PaymentExecuteArgs,
    PaymentExecuteResult,
    PolicyLookupArgs,
    PolicyLookupResult,
    RepairCostArgs,
    RepairCostResult,
    ReserveSetArgs,
    ReserveSetResult,
    SanctionsCheckArgs,
    SanctionsCheckResult,
    SemanticMatch,
    WeatherVerifyArgs,
    WeatherVerifyResult,
)

_RELEVANCE_FLOOR = 0.01  # fused-score floor below which retrieval is "no grounding"
_SEMANTIC_DUP_THRESHOLD = 0.82  # cosine threshold for a near-duplicate narrative


@dataclass
class RagContext:
    index: GuidelineIndex | None = None
    embedder: Embedder | None = None
    # claimant_id -> [(claim_id, narrative), ...] for semantic duplicate detection
    narratives: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


def _make_guideline_search(index: GuidelineIndex | None):  # type: ignore[no-untyped-def]
    async def handler(args: GuidelineSearchArgs) -> GuidelineSearchResult:
        if index is None:
            return GuidelineSearchResult(chunks=[], low_relevance=True)
        chunks = await index.search(args.query, args.k)
        out = [GuidelineChunkOut(**c.model_dump()) for c in chunks]
        low = not out or all(c.score < _RELEVANCE_FLOOR for c in out)
        return GuidelineSearchResult(chunks=out, low_relevance=low)

    return handler


def _make_duplicate_check(rag: RagContext | None):  # type: ignore[no-untyped-def]
    async def handler(args: DuplicateCheckArgs) -> DuplicateCheckResult:
        exact = (await handlers.duplicate_claim_check(args)).exact_matches
        semantic: list[SemanticMatch] = []
        if rag and rag.embedder and args.narrative:
            priors = rag.narratives.get(args.claimant_id, [])
            if priors:
                vecs = await rag.embedder.embed([args.narrative] + [p[1] for p in priors])
                q = vecs[0]
                for (cid, _), pv in zip(priors, vecs[1:], strict=False):
                    sim = cosine(q, pv)
                    if sim >= _SEMANTIC_DUP_THRESHOLD:
                        semantic.append(SemanticMatch(claim_id=cid, similarity=round(sim, 3)))
        semantic.sort(key=lambda m: -m.similarity)
        return DuplicateCheckResult(exact_matches=exact, semantic_matches=semantic)

    return handler


def build_registry(rag: RagContext | None = None) -> dict[str, Tool]:
    dup_handler = _make_duplicate_check(rag) if rag else handlers.duplicate_claim_check
    tools: list[Tool] = [
        Tool(name="policy_lookup", description="Fetch the policy record (mock).",
             args_schema=PolicyLookupArgs, result_schema=PolicyLookupResult,
             risk_tier=RiskTier.T0, idempotent=True, handler=handlers.policy_lookup),
        Tool(name="coverage_check", description="Rules-only coverage screen (grounded in RAG by the graph).",
             args_schema=CoverageCheckArgs, result_schema=CoverageCheckResult,
             risk_tier=RiskTier.T0, idempotent=False, handler=handlers.coverage_check),
        Tool(name="repair_cost_estimator", description="Line-item repair estimate (mock).",
             args_schema=RepairCostArgs, result_schema=RepairCostResult,
             risk_tier=RiskTier.T0, idempotent=True, handler=handlers.repair_cost_estimator),
        Tool(name="reserve_set", description="Set/adjust the reserve (T1, idempotent).",
             args_schema=ReserveSetArgs, result_schema=ReserveSetResult,
             risk_tier=RiskTier.T1, idempotent=True, handler=handlers.reserve_set),
        Tool(name="payment_execute", description="Disburse settlement (T2; requires authorization).",
             args_schema=PaymentExecuteArgs, result_schema=PaymentExecuteResult,
             risk_tier=RiskTier.T2, idempotent=True, handler=handlers.payment_execute),
        Tool(name="customer_comm_send", description="Draft (T0) or send (T2) a claimant comm.",
             args_schema=CommSendArgs, result_schema=CommSendResult,
             risk_tier=RiskTier.T2, idempotent=False, handler=handlers.customer_comm_send),
        Tool(name="claim_history", description="Claimant prior claims + 24m count (mock).",
             args_schema=ClaimHistoryArgs, result_schema=ClaimHistoryResult,
             risk_tier=RiskTier.T0, idempotent=True, handler=handlers.claim_history),
        Tool(name="duplicate_claim_check", description="Exact + semantic duplicate detection.",
             args_schema=DuplicateCheckArgs, result_schema=DuplicateCheckResult,
             risk_tier=RiskTier.T0, idempotent=True, handler=dup_handler),
        Tool(name="fraud_signal_scan", description="Fraud score + itemized signals (rules + semantic).",
             args_schema=FraudScanArgs, result_schema=FraudScanResult,
             risk_tier=RiskTier.T0, idempotent=False, handler=handlers.fraud_signal_scan),
        Tool(name="weather_event_verify", description="Corroborate a weather peril (mock NOAA).",
             args_schema=WeatherVerifyArgs, result_schema=WeatherVerifyResult,
             risk_tier=RiskTier.T0, idempotent=True, handler=handlers.weather_event_verify),
        Tool(name="sanctions_watchlist_check", description="OFAC-style payee screen (mandatory pre-payment).",
             args_schema=SanctionsCheckArgs, result_schema=SanctionsCheckResult,
             risk_tier=RiskTier.T0, idempotent=True, handler=handlers.sanctions_watchlist_check),
        Tool(name="document_request_create", description="Request documents; opens the W4 loop (T1).",
             args_schema=DocRequestArgs, result_schema=DocRequestResult,
             risk_tier=RiskTier.T1, idempotent=False, handler=handlers.document_request_create),
        Tool(name="escalate_to_human", description="Create a human task — the universal exit (T1).",
             args_schema=EscalateArgs, result_schema=EscalateResult,
             risk_tier=RiskTier.T1, idempotent=False, handler=handlers.escalate_to_human),
        Tool(name="guideline_search", description="Hybrid RAG retrieval over the guideline corpus.",
             args_schema=GuidelineSearchArgs, result_schema=GuidelineSearchResult,
             risk_tier=RiskTier.T0, idempotent=True, handler=_make_guideline_search(
                 rag.index if rag else None)),
    ]
    return {t.name: t for t in tools}

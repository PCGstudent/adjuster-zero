"""Phase 4 hardening tests: fail-closed sanctions → payment compensation
(reserve restored → REVIEW_PENDING), and replan-budget exhaustion → escalation."""

from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import MemorySaver

from adjuster_zero.config import get_settings
from adjuster_zero.domain.aggregate import ClaimAggregate
from adjuster_zero.domain.states import ClaimState
from adjuster_zero.graph.lifecycle import LifecycleDeps, resume_claim, run_claim
from adjuster_zero.llm import GeminiClient, TaskKind
from adjuster_zero.llm.client import LLMCallMeta
from adjuster_zero.persistence import InMemoryClaimStore
from adjuster_zero.planner.schemas import (
    ClaimClassification,
    ExtractedField,
    FnolExtraction,
    LetterDraft,
)
from adjuster_zero.router import RoutingConfig
from adjuster_zero.tools import ToolExecutor, build_registry


class FakeClient(GeminiClient):
    def __init__(self, ext: FnolExtraction, cls: ClaimClassification) -> None:
        super().__init__(api_key="fake")
        self._e, self._c = ext, cls

    async def generate_structured(self, task, prompt, schema, *, system=None, temperature=0.0, event_sink=None):  # type: ignore[override]
        meta = LLMCallMeta(model="flash-lite", tokens_in=80, tokens_out=30, latency_ms=8)
        if task == TaskKind.EXTRACT:
            return self._e, meta
        if task == TaskKind.LETTER:
            return LetterDraft(subject="x", body="y"), meta
        return self._c, meta


def _deps(client: GeminiClient, store: InMemoryClaimStore) -> LifecycleDeps:
    ex = ToolExecutor(build_registry(), recorder=store.record_tool_call)
    return LifecycleDeps(store=store, planner=client, executor=ex,
                         routing_config=RoutingConfig(), config_version=1)


def _glass(policy: str) -> FakeClient:
    ext = FnolExtraction(
        fields=[ExtractedField(name="policy_number", value=policy, confidence=0.99),
                ExtractedField(name="loss_date", value="2026-06-08", confidence=0.95),
                ExtractedField(name="loss_location", value="I-80 near Sacramento", confidence=0.9),
                ExtractedField(name="peril", value="glass", confidence=0.96)],
        missing_required=[], overall_completeness=1.0)
    return FakeClient(ext, ClaimClassification(line="auto", peril="glass", severity=1,
                                               complexity="low", confidence=0.95))


def test_sanctions_outage_compensates_and_parks() -> None:
    settings = get_settings()
    settings.sanctions_unavailable = True
    try:
        async def run() -> None:
            store = InMemoryClaimStore()
            agg = ClaimAggregate(id="CLM-SANC", fnol_text="glass POL-88341",
                                 claimant_id="CLMT-001", policy_number="POL-88341")
            final = await run_claim(agg, _deps(_glass("POL-88341"), store))
            # would auto-pay (W1), but sanctions is down → payment blocked → compensated
            assert final.state is ClaimState.REVIEW_PENDING
            assert final.reason_code == "COMPLIANCE_UNAVAILABLE"
            assert final.financials.paid == 0
            assert final.financials.reserve == 0  # reserve restored
            types = [e["type"] for e in store.events]
            assert "claim.compensated" in types
            assert "claim.settled" not in types

        asyncio.run(run())
    finally:
        settings.sanctions_unavailable = False


def test_replan_budget_exhaustion_escalates() -> None:
    settings = get_settings()
    original = settings.max_replans
    settings.max_replans = 0  # the first W4 resume already exceeds the budget
    try:
        async def run() -> None:
            store = InMemoryClaimStore()
            ext = FnolExtraction(
                fields=[ExtractedField(name="description", value="accident", confidence=0.6)],
                missing_required=["policy_number", "loss_date"], overall_completeness=0.4)
            client = FakeClient(ext, ClaimClassification(line="auto", peril="other", severity=2,
                                                         complexity="med", confidence=0.6))
            saver = MemorySaver()
            agg = ClaimAggregate(id="CLM-RP", fnol_text="accident", claimant_id="CLMT-003")
            paused = await run_claim(agg, _deps(client, store), checkpointer=saver, thread_id=agg.id)
            assert paused.state is ClaimState.INFO_PENDING

            final = await resume_claim(_deps(client, store), checkpointer=saver,
                                       thread_id=agg.id, resume_value={"fields": {}})
            assert final.state is ClaimState.ESCALATED
            assert final.reason_code == "REPLAN_LIMIT"

        asyncio.run(run())
    finally:
        settings.max_replans = original

"""End-to-end lifecycle tests with a fake planner (no network, no DB).

Proves Journey A (clean_glass → CLOSED with ≥6 tool calls), the lapsed-policy
park (W2, no payment tool reachable), and the missing-docs info loop (W4).
"""

from __future__ import annotations

import asyncio

from adjuster_zero.domain.aggregate import ClaimAggregate
from adjuster_zero.domain.states import ClaimState, Workflow
from adjuster_zero.graph.lifecycle import LifecycleDeps, run_claim
from adjuster_zero.llm import GeminiClient, TaskKind
from adjuster_zero.llm.client import LLMCallMeta
from adjuster_zero.persistence import InMemoryClaimStore
from adjuster_zero.planner.schemas import (
    ClaimClassification,
    ClassAlt,
    ExtractedField,
    FnolExtraction,
    LetterDraft,
)
from adjuster_zero.router import RoutingConfig
from adjuster_zero.seed.data import get_scenario
from adjuster_zero.tools import ToolExecutor, build_registry


class FakeGeminiClient(GeminiClient):
    """Returns canned extraction / classification / letter by task type."""

    def __init__(self, extraction: FnolExtraction, classification: ClaimClassification) -> None:
        super().__init__(api_key="fake")
        self._extraction = extraction
        self._classification = classification

    async def generate_structured(self, task, prompt, schema, *, system=None, temperature=0.0, event_sink=None):  # type: ignore[override]
        meta = LLMCallMeta(model="gemini-2.5-flash-lite", tokens_in=200, tokens_out=80, latency_ms=120)
        if task == TaskKind.EXTRACT:
            return self._extraction, meta
        if task == TaskKind.LETTER:
            return LetterDraft(subject="Your claim", body="We have reviewed your claim."), meta
        return self._classification, meta


def _deps(client: GeminiClient, store: InMemoryClaimStore) -> LifecycleDeps:
    executor = ToolExecutor(build_registry(), recorder=store.record_tool_call)
    return LifecycleDeps(
        store=store, planner=client, executor=executor,
        routing_config=RoutingConfig(), config_version=1,
    )


def _agg(scenario_key: str) -> ClaimAggregate:
    s = get_scenario(scenario_key)
    assert s is not None
    return ClaimAggregate(
        id=f"CLM-TEST-{scenario_key}",
        fnol_text=s.fnol_text,
        document_ids=s.document_ids,
        claimant_id=s.claimant_id,
        policy_number=s.policy_number,
    )


def _clean_extraction() -> FnolExtraction:
    return FnolExtraction(
        fields=[
            ExtractedField(name="policy_number", value="POL-88341", confidence=0.99),
            ExtractedField(name="loss_date", value="2026-06-08", confidence=0.95),
            ExtractedField(name="loss_location", value="I-80 near Sacramento", confidence=0.9),
            ExtractedField(name="peril", value="glass", confidence=0.96),
            ExtractedField(name="description", value="cracked windshield", confidence=0.93),
        ],
        missing_required=[],
        overall_completeness=1.0,
    )


def _glass_classification() -> ClaimClassification:
    return ClaimClassification(
        line="auto", peril="glass", severity=1, complexity="low",
        confidence=0.95, alternatives=[ClassAlt(label="collision", p=0.06)],
    )


def test_journey_a_clean_glass_closes() -> None:
    store = InMemoryClaimStore()
    client = FakeGeminiClient(_clean_extraction(), _glass_classification())

    async def run() -> None:
        final = await run_claim(_agg("clean_glass"), _deps(client, store))
        assert final.state is ClaimState.CLOSED
        assert final.workflow is Workflow.W1
        assert final.rule_id == "R-03"
        assert final.financials.paid > 0
        # ≥6 tool calls visible (3 read-only + reserve + payment + comm)
        assert len(store.tool_calls) >= 6
        tools = [t["tool"] for t in store.tool_calls]
        assert "payment_execute" in tools
        # routed + settled + closed events present
        types = [e["type"] for e in store.events]
        assert "claim.routed" in types
        assert "claim.closed" in types

    asyncio.run(run())


def test_journey_b_lapsed_policy_pauses_for_review_no_payment() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    store = InMemoryClaimStore()
    extraction = _clean_extraction().model_copy()
    extraction.fields[0] = ExtractedField(name="policy_number", value="POL-77120", confidence=0.99)
    client = FakeGeminiClient(extraction, _glass_classification())

    async def run() -> None:
        # W2 now pauses at the approval gate (interrupt) → needs a checkpointer.
        final = await run_claim(_agg("lapsed_policy"), _deps(client, store), checkpointer=MemorySaver())
        assert final.workflow is Workflow.W2
        assert final.rule_id == "R-02"
        assert final.state is ClaimState.REVIEW_PENDING
        # A pending approval was created; no payment ever executed.
        assert len(await store.list_pending_approvals()) == 1
        assert "payment_execute" not in [t["tool"] for t in store.tool_calls]
        assert final.financials.paid == 0

    asyncio.run(run())


def test_journey_e_missing_docs_pauses_info_pending() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    store = InMemoryClaimStore()
    extraction = FnolExtraction(
        fields=[ExtractedField(name="description", value="accident, car damaged", confidence=0.6)],
        missing_required=["policy_number", "loss_date", "loss_location"],
        overall_completeness=0.45,
    )
    classification = ClaimClassification(
        line="auto", peril="other", severity=2, complexity="med", confidence=0.6,
    )
    client = FakeGeminiClient(extraction, classification)

    async def run() -> None:
        final = await run_claim(_agg("missing_docs"), _deps(client, store), checkpointer=MemorySaver())
        assert final.workflow is Workflow.W4
        assert final.rule_id == "R-01"
        assert final.state is ClaimState.INFO_PENDING
        assert "payment_execute" not in [t["tool"] for t in store.tool_calls]

    asyncio.run(run())


def test_budget_exhaustion_escalates() -> None:
    store = InMemoryClaimStore()

    class BigTokenClient(FakeGeminiClient):
        async def generate_structured(self, task, prompt, schema, *, system=None, temperature=0.0, event_sink=None):  # type: ignore[override]
            obj, meta = await super().generate_structured(task, prompt, schema)
            meta.tokens_out = 10_000_000  # blow the budget on the first call
            return obj, meta

    client = BigTokenClient(_clean_extraction(), _glass_classification())

    async def run() -> None:
        final = await run_claim(_agg("clean_glass"), _deps(client, store))
        assert final.state is ClaimState.ESCALATED
        assert final.reason_code == "TOKEN_BUDGET_EXHAUSTED"
        assert "claim.escalated" in [e["type"] for e in store.events]

    asyncio.run(run())

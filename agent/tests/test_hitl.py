"""Phase 2 HITL tests: interrupt/resume round-trips (Journeys B & D), the W4
document loop, and restart survival of a paused claim.

All in-memory: a MemorySaver stands in for the Postgres checkpointer; a fresh
graph/executor on resume proves state lives in the checkpointer, not the objects.
"""

from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import MemorySaver

from adjuster_zero.domain.aggregate import ClaimAggregate
from adjuster_zero.domain.states import ClaimState, Workflow
from adjuster_zero.graph.lifecycle import (
    LifecycleDeps,
    approval_id_for,
    resume_claim,
    run_claim,
)
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
    def __init__(self, extraction: FnolExtraction, classification: ClaimClassification) -> None:
        super().__init__(api_key="fake")
        self._e = extraction
        self._c = classification

    async def generate_structured(self, task, prompt, schema, *, system=None, temperature=0.0, event_sink=None):  # type: ignore[override]
        meta = LLMCallMeta(model="flash-lite", tokens_in=100, tokens_out=40, latency_ms=10)
        if task == TaskKind.EXTRACT:
            return self._e, meta
        if task == TaskKind.LETTER:
            return LetterDraft(subject="Decision on your claim",
                               body="After review, your claim is denied: policy lapsed."), meta
        return self._c, meta


def _deps(client: GeminiClient, store: InMemoryClaimStore) -> LifecycleDeps:
    ex = ToolExecutor(build_registry(), recorder=store.record_tool_call)
    return LifecycleDeps(store=store, planner=client, executor=ex,
                         routing_config=RoutingConfig(), config_version=1)


def _agg(claim_id: str, policy: str | None, fnol: str = "claim") -> ClaimAggregate:
    return ClaimAggregate(id=claim_id, fnol_text=fnol, claimant_id="CLMT-001", policy_number=policy)


def _extraction(policy: str, peril: str = "glass", complete: float = 1.0) -> FnolExtraction:
    return FnolExtraction(
        fields=[
            ExtractedField(name="policy_number", value=policy, confidence=0.99),
            ExtractedField(name="loss_date", value="2026-06-08", confidence=0.95),
            ExtractedField(name="loss_location", value="I-80", confidence=0.9),
            ExtractedField(name="peril", value=peril, confidence=0.95),
        ],
        missing_required=[], overall_completeness=complete,
    )


def _cls(peril: str = "glass", severity: int = 1) -> ClaimClassification:
    return ClaimClassification(line="auto", peril=peril, severity=severity, complexity="low",
                               confidence=0.95)


# ── Journey B: refusal → human approves → DENIED ─────────────────────────────
def test_w2_deny_round_trip() -> None:
    store = InMemoryClaimStore()
    saver = MemorySaver()
    client = FakeClient(_extraction("POL-77120"), _cls("glass"))
    deps = _deps(client, store)
    agg = _agg("CLM-B", "POL-77120")

    async def run() -> None:
        paused = await run_claim(agg, deps, checkpointer=saver, thread_id=agg.id)
        assert paused.state is ClaimState.REVIEW_PENDING
        assert paused.workflow is Workflow.W2 and paused.rule_id == "R-02"
        pend = await store.list_pending_approvals()
        assert len(pend) == 1 and pend[0]["requested_action"]["type"] == "deny"

        final = await resume_claim(deps, checkpointer=saver, thread_id=agg.id,
                                   resume_value={"resolution": "approve", "resolved_by": "dana"})
        assert final.state is ClaimState.DENIED
        # denial letter was actually sent (T2 send, gated by approval_ref)
        sends = [t for t in store.tool_calls
                 if t["tool"] == "customer_comm_send" and t["args"].get("mode") == "send"]
        assert sends and sends[0]["status"] == "ok"
        assert "payment_execute" not in [t["tool"] for t in store.tool_calls]
        appr = await store.get_approval(approval_id_for("CLM-B"))
        assert appr["status"] == "approved"

    asyncio.run(run())


# ── Journey D: W2 payout proposed → human MODIFIES the amount → settled ──────
def test_w2_pay_modify_uses_my_amount() -> None:
    store = InMemoryClaimStore()
    saver = MemorySaver()
    # collision on an active policy → 2800 estimate > 2500 ceiling → R-99 W2 (pay)
    client = FakeClient(_extraction("POL-88341", peril="collision"), _cls("collision", severity=2))
    deps = _deps(client, store)
    agg = _agg("CLM-D", "POL-88341")

    async def run() -> None:
        paused = await run_claim(agg, deps, checkpointer=saver, thread_id=agg.id)
        assert paused.state is ClaimState.REVIEW_PENDING
        assert paused.workflow is Workflow.W2
        appr = await store.get_approval(approval_id_for("CLM-D"))
        assert appr["requested_action"]["type"] == "pay"
        assert appr["requested_action"]["amount"] == 2800

        final = await resume_claim(
            deps, checkpointer=saver, thread_id=agg.id,
            resume_value={"resolution": "modify", "delta": {"amount": 2000},
                          "reason_code": "depreciation", "resolved_by": "marcus"})
        assert final.state is ClaimState.CLOSED
        assert final.financials.paid == 2000  # MY amount, not the proposed 2800
        appr2 = await store.get_approval(approval_id_for("CLM-D"))
        assert appr2["status"] == "modified"
        assert appr2["delta"] == {"amount": 2000}
        assert appr2["reason_code"] == "depreciation"

    asyncio.run(run())


# ── Journey E: W4 info loop → documents arrive → re-triage → settle ──────────
def test_w4_resume_to_closed() -> None:
    store = InMemoryClaimStore()
    saver = MemorySaver()
    # Arrives genuinely incomplete: we can see it's a glass loss and where, but not
    # the policy number or loss date → deterministic completeness < 0.9 → R-01 → W4.
    incomplete = FnolExtraction(
        fields=[ExtractedField(name="loss_location", value="I-80 near Sacramento", confidence=0.9),
                ExtractedField(name="peril", value="glass", confidence=0.95)],
        missing_required=["policy_number", "loss_date"], overall_completeness=0.4)
    client = FakeClient(incomplete, _cls("glass"))
    deps = _deps(client, store)
    agg = _agg("CLM-E", policy=None)

    async def run() -> None:
        paused = await run_claim(agg, deps, checkpointer=saver, thread_id=agg.id)
        assert paused.state is ClaimState.INFO_PENDING and paused.workflow is Workflow.W4

        final = await resume_claim(
            deps, checkpointer=saver, thread_id=agg.id,
            resume_value={"fields": {"policy_number": "POL-90013", "loss_date": "2026-06-05"}})
        # docs complete the claim → re-triage → glass on active policy → W1 → CLOSED
        assert final.state is ClaimState.CLOSED
        assert "claim.document_received" in [e["type"] for e in store.events]

    asyncio.run(run())


# ── Restart survival: a fresh graph/executor resumes a paused claim ──────────
def test_restart_survival_resumes_paused_claim() -> None:
    store = InMemoryClaimStore()
    saver = MemorySaver()  # stands in for the durable Postgres checkpointer
    client = FakeClient(_extraction("POL-77120"), _cls("glass"))
    agg = _agg("CLM-R", "POL-77120")

    async def run() -> None:
        paused = await run_claim(agg, _deps(client, store), checkpointer=saver, thread_id=agg.id)
        assert paused.state is ClaimState.REVIEW_PENDING

        # Simulate a restart: brand-new deps (new executor) sharing only the
        # checkpointer + store. State must live in the checkpointer, not objects.
        fresh_deps = _deps(client, store)
        final = await resume_claim(fresh_deps, checkpointer=saver, thread_id=agg.id,
                                   resume_value={"resolution": "approve"})
        assert final.state is ClaimState.DENIED

    asyncio.run(run())

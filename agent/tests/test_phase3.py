"""Phase 3 tests: RAG retrieval, semantic duplicate detection, citation-coverage
floor (thesis 8), Journey C (fraud → W3, no payment), and degraded-mode capping.
All offline (LocalHashEmbedder + in-memory index)."""

from __future__ import annotations

import asyncio

from adjuster_zero.config import get_settings
from adjuster_zero.domain.aggregate import ClaimAggregate
from adjuster_zero.domain.states import ClaimState, Workflow
from adjuster_zero.graph.lifecycle import LifecycleDeps, run_claim
from adjuster_zero.llm import GeminiClient, TaskKind
from adjuster_zero.llm.client import LLMCallMeta
from adjuster_zero.persistence import InMemoryClaimStore
from adjuster_zero.planner.coverage import CoverageDetermination, apply_citation_floor
from adjuster_zero.planner.schemas import ClaimClassification, ExtractedField, FnolExtraction
from adjuster_zero.rag.embed import LocalHashEmbedder
from adjuster_zero.rag.index import InMemoryGuidelineIndex
from adjuster_zero.router import RoutingConfig
from adjuster_zero.seed.data import CLAIM_HISTORY
from adjuster_zero.tools import RagContext, ToolExecutor, build_registry
from adjuster_zero.tools.schemas import DuplicateCheckArgs


def _narratives() -> dict[str, list[tuple[str, str]]]:
    return {cid: [(c["claim_id"], c.get("narrative", "")) for c in cl]
            for cid, cl in CLAIM_HISTORY.items()}


async def _rag() -> RagContext:
    emb = LocalHashEmbedder()
    return RagContext(index=await InMemoryGuidelineIndex.build(emb), embedder=emb,
                      narratives=_narratives())


class FakeClient(GeminiClient):
    def __init__(self, ext: FnolExtraction, cls: ClaimClassification) -> None:
        super().__init__(api_key="fake")
        self._e, self._c = ext, cls

    async def generate_structured(self, task, prompt, schema, *, system=None, temperature=0.0, event_sink=None):  # type: ignore[override]
        meta = LLMCallMeta(model="flash-lite", tokens_in=80, tokens_out=30, latency_ms=8)
        return (self._e if task == TaskKind.EXTRACT else self._c), meta


# ── RAG retrieval ────────────────────────────────────────────────────────────
def test_guideline_index_retrieves_relevant_doc() -> None:
    async def run() -> None:
        idx = await InMemoryGuidelineIndex.build(LocalHashEmbedder())
        assert idx.size() >= 12  # ~12 docs, multiple sections
        hits = await idx.search("windshield glass deductible comprehensive", k=3)
        assert hits
        assert any(h.doc == "G-AUTO-GLASS" for h in hits)

    asyncio.run(run())


# ── Semantic duplicate detection (paraphrase still matches) ──────────────────
def test_semantic_duplicate_matches_paraphrase() -> None:
    async def run() -> None:
        reg = build_registry(await _rag())
        handler = reg["duplicate_claim_check"].handler
        # Paraphrase of CLMT-004's theft prior, with a DIFFERENT peril so the
        # EXACT matcher does not fire — only semantics can catch it.
        args = DuplicateCheckArgs(
            claim_id="CLM-NEW", claimant_id="CLMT-004", peril="water",
            narrative="Someone broke into my parked car overnight in the driveway "
                      "and stole the laptop bag and tools from the trunk.")
        res = await handler(args)
        assert res.exact_matches == []
        assert res.semantic_matches, "paraphrase should match semantically"
        assert res.semantic_matches[0].claim_id == "CLM-2025-09112"
        assert res.semantic_matches[0].similarity >= 0.82

    asyncio.run(run())


# ── Citation floor (thesis 8) ────────────────────────────────────────────────
def test_citation_floor_uncited_determination() -> None:
    det = CoverageDetermination(covered=True, confidence=0.95, citations=[])
    coverage, guard = apply_citation_floor(det, {"G-AUTO-GLASS#c0"})
    assert coverage.confidence == 0.5  # floored
    assert guard["confidence_floored"] is True
    assert guard["citation_coverage"] == 0.0


def test_citation_floor_cited_determination_not_floored() -> None:
    det = CoverageDetermination(covered=True, confidence=0.94, citations=["G-AUTO-GLASS#c0"])
    coverage, guard = apply_citation_floor(det, {"G-AUTO-GLASS#c0", "G-AUTO-COMP#c1"})
    assert coverage.confidence == 0.94
    assert coverage.citations == ["G-AUTO-GLASS#c0"]
    assert guard["confidence_floored"] is False


class CoverageFakeClient(GeminiClient):
    """Handles EXTRACT/CLASSIFY plus a configurable grounded COVERAGE result."""

    def __init__(self, ext: FnolExtraction, cls: ClaimClassification,
                 det: CoverageDetermination) -> None:
        super().__init__(api_key="fake")
        self._e, self._c, self._d = ext, cls, det

    async def generate_structured(self, task, prompt, schema, *, system=None, temperature=0.0, event_sink=None):  # type: ignore[override]
        meta = LLMCallMeta(model="flash", tokens_in=120, tokens_out=50, latency_ms=15)
        if task == TaskKind.EXTRACT:
            return self._e, meta
        if task == TaskKind.COVERAGE:
            return self._d, meta
        return self._c, meta


def test_uncited_grounded_determination_routes_to_human_review() -> None:
    """End-to-end (thesis 8): a grounded coverage determination with NO valid
    citation is confidence-floored to 0.5 → router sends it to W5 human review."""
    async def run() -> None:
        store = InMemoryClaimStore()
        ext = FnolExtraction(
            fields=[ExtractedField(name="policy_number", value="POL-88341", confidence=0.99),
                    ExtractedField(name="loss_date", value="2026-06-08", confidence=0.95),
                    ExtractedField(name="loss_location", value="I-80 near Sacramento", confidence=0.9),
                    ExtractedField(name="peril", value="glass", confidence=0.96)],
            missing_required=[], overall_completeness=1.0)
        cls = ClaimClassification(line="auto", peril="glass", severity=1, complexity="low",
                                  confidence=0.95)
        det = CoverageDetermination(covered=True, confidence=0.95, citations=[])  # uncited!
        executor = ToolExecutor(build_registry(await _rag()), recorder=store.record_tool_call)
        deps = LifecycleDeps(store=store, planner=CoverageFakeClient(ext, cls, det),
                             executor=executor, routing_config=RoutingConfig(),
                             config_version=1, ground_coverage=True)
        from langgraph.checkpoint.memory import MemorySaver
        agg = ClaimAggregate(id="CLM-UNCITED", fnol_text="windshield crack POL-88341",
                             claimant_id="CLMT-001", policy_number="POL-88341")
        final = await run_claim(agg, deps, checkpointer=MemorySaver())
        assert final.coverage.confidence == 0.5  # floored
        assert final.workflow is Workflow.W5  # forced to human review
        assert "payment_execute" not in [t["tool"] for t in store.tool_calls]

    asyncio.run(run())


# ── Journey C: fraud → W3, no payment reachable ──────────────────────────────
def test_journey_c_fraud_routes_w3_no_payment() -> None:
    async def run() -> None:
        store = InMemoryClaimStore()
        ext = FnolExtraction(
            fields=[ExtractedField(name="policy_number", value="POL-55200", confidence=0.99),
                    ExtractedField(name="loss_date", value="2026-06-08", confidence=0.95),
                    ExtractedField(name="loss_location", value="driveway, Oakland", confidence=0.9),
                    ExtractedField(name="peril", value="theft", confidence=0.95)],
            missing_required=[], overall_completeness=1.0)
        cls = ClaimClassification(line="auto", peril="theft", severity=2, complexity="low",
                                  confidence=0.95)
        executor = ToolExecutor(build_registry(await _rag()), recorder=store.record_tool_call)
        deps = LifecycleDeps(store=store, planner=FakeClient(ext, cls), executor=executor,
                             routing_config=RoutingConfig(), config_version=1)
        agg = ClaimAggregate(
            id="CLM-C", fnol_text="My car was broken into overnight while parked in my "
            "driveway and my laptop bag and tools were stolen out of the trunk again.",
            claimant_id="CLMT-004", policy_number="POL-55200")
        final = await run_claim(agg, deps)
        assert final.workflow is Workflow.W3
        assert final.state is ClaimState.ESCALATED
        assert final.fraud_score > 0.70
        assert len(final.fraud_signals) >= 3
        assert "payment_execute" not in [t["tool"] for t in store.tool_calls]

    asyncio.run(run())


# ── Degraded fraud control → cap at W2 (no STP) ──────────────────────────────
def test_degraded_mode_caps_w1_to_w2() -> None:
    settings = get_settings()
    settings.fraud_controls_degraded = True
    try:
        async def run() -> None:
            store = InMemoryClaimStore()
            ext = FnolExtraction(
                fields=[ExtractedField(name="policy_number", value="POL-88341", confidence=0.99),
                        ExtractedField(name="loss_date", value="2026-06-08", confidence=0.95),
                        ExtractedField(name="loss_location", value="I-80 near Sacramento", confidence=0.9),
                        ExtractedField(name="peril", value="glass", confidence=0.96)],
                missing_required=[], overall_completeness=1.0)
            cls = ClaimClassification(line="auto", peril="glass", severity=1, complexity="low",
                                      confidence=0.95)
            executor = ToolExecutor(build_registry(await _rag()), recorder=store.record_tool_call)
            deps = LifecycleDeps(store=store, planner=FakeClient(ext, cls), executor=executor,
                                 routing_config=RoutingConfig(), config_version=1)
            from langgraph.checkpoint.memory import MemorySaver
            agg = ClaimAggregate(id="CLM-DEG", fnol_text="glass crack POL-88341",
                                 claimant_id="CLMT-001", policy_number="POL-88341")
            final = await run_claim(agg, deps, checkpointer=MemorySaver())
            # would be W1 STP, but the degraded control caps it at W2 (no auto-pay)
            assert final.workflow is Workflow.W2
            assert final.rule_id == "R-DEGRADED"
            assert "control.degraded_mode" in [e["type"] for e in store.events]
            assert "payment_execute" not in [t["tool"] for t in store.tool_calls]

        asyncio.run(run())
    finally:
        settings.fraud_controls_degraded = False

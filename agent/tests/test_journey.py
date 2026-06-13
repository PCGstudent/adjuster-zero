"""The step-by-step walkthrough is a PURE projection of a claim's persisted trace
(decisions + tool calls + events) — no LLM, no side effects. Run a clean-glass
claim end to end, then assert the journey reads input → output → explanation across
every phase and exposes the deterministic route step faithfully.
"""

from __future__ import annotations

import asyncio

from adjuster_zero.api.journey import build_journey
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


class FakeClient(GeminiClient):
    def __init__(self, extraction: FnolExtraction, classification: ClaimClassification) -> None:
        super().__init__(api_key="fake")
        self._e = extraction
        self._c = classification

    async def generate_structured(self, task, prompt, schema, *, system=None, temperature=0.0, event_sink=None):  # type: ignore[override]
        meta = LLMCallMeta(model="gemini-2.5-flash-lite", tokens_in=200, tokens_out=80, latency_ms=120)
        if task == TaskKind.EXTRACT:
            return self._e, meta
        if task == TaskKind.LETTER:
            return LetterDraft(subject="x", body="y"), meta
        return self._c, meta


def _clean() -> FnolExtraction:
    return FnolExtraction(
        fields=[ExtractedField(name="policy_number", value="POL-88341", confidence=0.99),
                ExtractedField(name="loss_date", value="2026-06-08", confidence=0.95),
                ExtractedField(name="loss_location", value="I-80 near Sacramento", confidence=0.9),
                ExtractedField(name="peril", value="glass", confidence=0.96),
                ExtractedField(name="description", value="cracked windshield", confidence=0.93)],
        missing_required=[], overall_completeness=1.0)


def _cls() -> ClaimClassification:
    return ClaimClassification(line="auto", peril="glass", severity=1, complexity="low",
                               confidence=0.95, alternatives=[ClassAlt(label="collision", p=0.05)])


def _agg() -> ClaimAggregate:
    s = get_scenario("clean_glass")
    assert s is not None
    return ClaimAggregate(id="CLM-J", fnol_text=s.fnol_text, claimant_id=s.claimant_id,
                          policy_number=s.policy_number)


def test_journey_replays_clean_glass_end_to_end() -> None:
    store = InMemoryClaimStore()
    executor = ToolExecutor(build_registry(), recorder=store.record_tool_call)
    deps = LifecycleDeps(store=store, planner=FakeClient(_clean(), _cls()), executor=executor,
                         routing_config=RoutingConfig(), config_version=1)

    async def run() -> None:
        final = await run_claim(_agg(), deps)
        assert final.state is ClaimState.CLOSED and final.workflow is Workflow.W1

        j = build_journey(
            await store.get_claim("CLM-J"),
            await store.get_events("CLM-J"),
            await store.get_decisions("CLM-J"),
            await store.get_tool_calls("CLM-J"))
        steps = j["steps"]

        # bookends + contiguous indices
        assert steps[0]["phase"] == "RECEIVE"
        assert steps[-1]["phase"] == "RESOLVE"
        assert [s["index"] for s in steps] == list(range(len(steps)))

        # every step carries an input, an output and a real explanation
        for s in steps:
            assert "value" in s["input"] and "value" in s["output"]
            assert len(s["explanation"]) > 20

        # the determinative phases all appear, and the diagram flags them active
        phases = {s["phase"] for s in steps}
        assert {"EXTRACT", "CLASSIFY", "INVESTIGATE", "ROUTE", "EXECUTE", "RESOLVE"} <= phases
        assert all(p["active"] for p in j["phases"] if p["key"] in phases)

        # the route step exposes the typed RouterInput as INPUT and the rule as OUTPUT
        route = next(s for s in steps if s["phase"] == "ROUTE" and s["actor"] == "orchestrator")
        assert route["output"]["value"]["workflow"] == "W1"
        assert isinstance(route["input"]["value"], dict) and "fraud_score" in route["input"]["value"]

        # extract step shows the deterministic completeness, not the LLM self-score, as authority
        ext = next(s for s in steps if s["phase"] == "EXTRACT")
        assert ext["output"]["value"]["deterministic_completeness"] == 1.0

        # payment_execute appears and its explanation teaches the structural gate
        pay = next(s for s in steps if s["meta"].get("tool") == "payment_execute")
        assert "unrepresentable" in pay["explanation"]

    asyncio.run(run())

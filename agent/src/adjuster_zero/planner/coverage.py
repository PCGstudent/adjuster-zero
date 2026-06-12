"""Grounded coverage determination + citation enforcement (thesis 8).

determine_coverage asks flash for a coverage decision grounded in retrieved
guideline chunks; the schema REQUIRES citations. apply_citation_floor then
verifies citation coverage against the actually-retrieved chunk ids and floors
confidence to 0.5 when a determinative claim is uncited — which (via the router's
coverage_conf_low) forces human review.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain.aggregate import Coverage
from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta

_FLOOR = 0.5
_SYSTEM = (
    "You are a coverage adjudicator. Decide whether the loss is covered, grounded "
    "ONLY in the provided guideline chunks. Cite the chunk id(s) that support your "
    "determination in `citations`. If the chunks do not support a determination, "
    "say covered=false with low confidence and cite nothing. Never invent policy terms."
)


class CoverageDetermination(BaseModel):
    covered: bool
    confidence: float = Field(ge=0, le=1)
    applicable_coverage: str | None = None
    exclusions_triggered: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    rationale: str = ""


async def determine_coverage(
    client: GeminiClient,
    *,
    query: str,
    chunks: list[dict],
    event_sink: EventSink | None = None,
) -> tuple[CoverageDetermination, LLMCallMeta]:
    corpus = "\n".join(f"[{c['id']}] {c['text']}" for c in chunks) or "(no guidelines retrieved)"
    prompt = f"Question: is this loss covered?\n{query}\n\nGuideline chunks:\n{corpus}"
    return await client.generate_structured(
        TaskKind.COVERAGE, prompt, CoverageDetermination, system=_SYSTEM, event_sink=event_sink
    )


def apply_citation_floor(det: CoverageDetermination, retrieved_ids: set[str]) -> tuple[Coverage, dict]:
    """Validate citation coverage and floor confidence if uncited. Returns the
    Coverage projection plus a guardrail dict for the decision log."""
    valid = [c for c in det.citations if c in retrieved_ids]
    # A determinative coverage/denial claim must be backed by a retrieved chunk.
    fully_cited = bool(valid)
    confidence = det.confidence if fully_cited else min(det.confidence, _FLOOR)
    coverage = Coverage(
        covered=det.covered,
        confidence=round(confidence, 2),
        applicable_coverage=det.applicable_coverage,
        exclusions_triggered=det.exclusions_triggered,
        citations=valid,
        rationale=det.rationale,
    )
    guardrails = {
        "citation_coverage": 1.0 if fully_cited else 0.0,
        "confidence_floored": not fully_cited,
        "cited_ids": valid,
    }
    return coverage, guardrails

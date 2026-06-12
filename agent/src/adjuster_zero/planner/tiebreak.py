"""R-06 ambiguous-band tiebreak (the ONLY place the LLM influences routing).

When fraud sits in [0.30, 0.70] the deterministic router defers; flash, grounded
in retrieved fraud-screening guidelines, chooses W2 (standard adjudication) or W3
(fraud). The decision is persisted with alternatives + rationale (thesis 2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta

_SYSTEM = (
    "You break ties in the ambiguous fraud band. Given the fraud signals and the "
    "fraud-screening guidelines, choose W2 (standard adjudication, human approves) "
    "or W3 (fraud investigation, no payment). Prefer W3 when hard signals cluster. "
    "Return your choice, a confidence, alternatives with probabilities, and a reason."
)


class TiebreakAlt(BaseModel):
    workflow: str
    p: float = Field(ge=0, le=1)


class TiebreakDecision(BaseModel):
    workflow: Literal["W2", "W3"]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    alternatives: list[TiebreakAlt] = Field(default_factory=list)


async def decide_tiebreak(
    client: GeminiClient,
    *,
    context: str,
    chunks: list[dict],
    event_sink: EventSink | None = None,
) -> tuple[TiebreakDecision, LLMCallMeta]:
    corpus = "\n".join(f"[{c['id']}] {c['text']}" for c in chunks) or "(no guidelines)"
    prompt = f"Fraud context:\n{context}\n\nGuidelines:\n{corpus}\n\nChoose W2 or W3."
    return await client.generate_structured(
        TaskKind.TIEBREAK, prompt, TiebreakDecision, system=_SYSTEM, event_sink=event_sink
    )

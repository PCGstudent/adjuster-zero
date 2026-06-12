"""explain_claim — an agent that explains a claim's automated decision in plain
language, grounded ONLY in the claim's own audit trail (events, decisions, the
rule that fired, citations). This is RAG over the system's own paper trail: the
answer to 'can I trust this, and why did it decide that?'
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta

_SYSTEM = (
    "You explain an insurance claim's automated decision to a curious person. Use "
    "ONLY the facts in the provided trace: the events, the agent decisions, the "
    "routing rule that fired, and any guideline citations. Be accurate and concrete "
    "— name the rule id and the cited guideline ids. Produce: a one-paragraph "
    "plain-language summary a non-expert can follow, and a short ordered list of the "
    "key steps with a one-line detail each. Never invent facts not in the trace."
)


class ExplanationStep(BaseModel):
    label: str
    detail: str


class Explanation(BaseModel):
    summary: str = Field(description="One paragraph, plain language, for a non-expert.")
    steps: list[ExplanationStep] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list, description="guideline/rule ids referenced")


async def explain_claim(
    client: GeminiClient, *, context: str, event_sink: EventSink | None = None
) -> tuple[Explanation, LLMCallMeta]:
    prompt = f"Explain this claim's outcome.\n\nTrace:\n{context}"
    return await client.generate_structured(
        TaskKind.EXPLAIN, prompt, Explanation, system=_SYSTEM, event_sink=event_sink
    )

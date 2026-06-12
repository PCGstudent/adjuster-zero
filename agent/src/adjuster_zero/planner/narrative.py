"""assess_narrative — a flash-lite plausibility / coherence screen on the FNOL.

This is the LLM half of fraud_signal_scan v2. A physically impossible,
fantastical, or self-contradictory loss cause is NOT plausible and must not be
straight-through processed — it becomes a high-weight fraud signal that pushes
the claim out of the STP band and into human review. Mundane losses pass
untouched, so clean claims still auto-settle.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta

_SYSTEM = (
    "You screen an insurance loss narrative for PLAUSIBILITY and internal "
    "COHERENCE. A cause that is physically impossible, fantastical/fictional "
    "(e.g. aliens, monsters, magic), or self-contradictory is NOT plausible. A "
    "normal, mundane loss (rock, hail, collision, theft, water) IS plausible. Be "
    "strict about impossible/fictional causes; do NOT penalize merely unusual but "
    "physically-possible events. List the specific anomalies you found."
)


class NarrativeAssessment(BaseModel):
    plausible: bool
    coherence: float = Field(ge=0, le=1, description="0 = incoherent/impossible, 1 = fully coherent.")
    anomalies: list[str] = Field(default_factory=list)
    reason: str = ""


async def assess_narrative(
    client: GeminiClient, fnol_text: str, *, event_sink: EventSink | None = None
) -> tuple[NarrativeAssessment, LLMCallMeta]:
    prompt = f"Loss narrative:\n\"\"\"\n{fnol_text}\n\"\"\"\n\nIs it plausible and coherent?"
    return await client.generate_structured(
        TaskKind.NARRATIVE, prompt, NarrativeAssessment, system=_SYSTEM, event_sink=event_sink
    )

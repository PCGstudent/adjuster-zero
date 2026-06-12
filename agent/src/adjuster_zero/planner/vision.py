"""describe_damage — multimodal intake. Gemini (flash-lite, vision) looks at a
photo of the loss and turns it into a First Notice of Loss narrative + a peril and
severity hint, which then flows through the same deterministic pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta

_SYSTEM = (
    "You are a claims intake assistant looking at a photo of damage. Describe ONLY "
    "what is visible as a concise First Notice of Loss narrative (1-2 sentences). "
    "Pick the most likely peril (glass | collision | hail | theft | water | fire | "
    "other), list the visible damage items, and give a severity hint 1-5. Do not "
    "invent a cause, policy, or injuries you cannot see."
)


class VisionFnol(BaseModel):
    description: str = Field(description="A short FNOL narrative of the visible damage.")
    peril: str
    visible_damage: list[str] = Field(default_factory=list)
    severity_hint: int = Field(ge=1, le=5, default=2)


async def describe_damage(
    client: GeminiClient, image_bytes: bytes, mime: str, *, event_sink: EventSink | None = None
) -> tuple[VisionFnol, LLMCallMeta]:
    return await client.generate_structured(
        TaskKind.VISION, "Describe the damage in this photo.", VisionFnol,
        system=_SYSTEM, images=[(image_bytes, mime)], event_sink=event_sink,
    )

"""claim_classifier (T-04) — line/peril/severity/complexity with alternatives.

flash-lite via GeminiClient, schema-validated with one repair retry.
"""

from __future__ import annotations

from typing import Any

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta
from .schemas import ClaimClassification

_SYSTEM = (
    "You are a claims classifier. Given the FNOL text and extracted fields, classify "
    "line (auto|property|injury), peril, severity 1-5, complexity (low|med|high), and "
    "the injury/attorney flags. Provide up to 2 alternative labels with probabilities. "
    "If the top-2 margin is small, lower your confidence rather than guessing."
)


async def classify_claim(
    client: GeminiClient,
    fnol_text: str,
    fields: dict[str, Any],
    *,
    event_sink: EventSink | None = None,
) -> tuple[ClaimClassification, LLMCallMeta]:
    prompt = (
        f"FNOL text:\n\"\"\"\n{fnol_text}\n\"\"\"\n\n"
        f"Extracted fields: {fields}\n\nClassify the claim."
    )
    return await client.generate_structured(
        TaskKind.CLASSIFY, prompt, ClaimClassification, system=_SYSTEM, event_sink=event_sink
    )

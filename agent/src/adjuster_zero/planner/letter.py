"""draft_letter — generate a claimant letter (e.g. a denial) with flash.

The fast-deny path drafts the denial letter with the larger model (quality
matters in customer-facing prose); the executor then sends it via
customer_comm_send. Output is schema-validated like every other LLM call.
"""

from __future__ import annotations

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta
from .schemas import LetterDraft

_SYSTEM = (
    "You draft concise, empathetic, factually accurate insurance claim letters. "
    "Cite the concrete reason given. Do not invent policy terms. Keep it under 120 words."
)


async def draft_letter(
    client: GeminiClient,
    *,
    claim_id: str,
    kind: str,
    context: str,
    event_sink: EventSink | None = None,
) -> tuple[LetterDraft, LLMCallMeta]:
    prompt = (
        f"Draft a {kind} letter for claim {claim_id}.\n"
        f"Context / reason to cite:\n{context}\n\n"
        "Return a subject and body."
    )
    return await client.generate_structured(
        TaskKind.LETTER, prompt, LetterDraft, system=_SYSTEM, event_sink=event_sink
    )

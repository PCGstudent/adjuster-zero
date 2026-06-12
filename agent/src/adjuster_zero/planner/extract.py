"""extract_fnol_fields (T-01) — FNOL text → typed fields + per-field confidence.

flash-lite via GeminiClient, schema-validated with one repair retry. Returns the
validated model plus call metadata for the decision log.
"""

from __future__ import annotations

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta
from .schemas import FnolExtraction

_SYSTEM = (
    "You are a claims intake extractor. Read the First Notice of Loss and extract "
    "structured fields. Required fields for an auto claim are: policy_number, "
    "loss_date (ISO YYYY-MM-DD), loss_location, peril, description. List any "
    "required field you cannot find in `missing_required`. Set overall_completeness "
    "to the fraction of required fields confidently present. Never invent a value; "
    "use null and lower confidence when unsure."
)


async def extract_fnol_fields(
    client: GeminiClient,
    fnol_text: str,
    *,
    event_sink: EventSink | None = None,
) -> tuple[FnolExtraction, LLMCallMeta]:
    prompt = f"FNOL text:\n\"\"\"\n{fnol_text}\n\"\"\"\n\nExtract the fields."
    return await client.generate_structured(
        TaskKind.EXTRACT, prompt, FnolExtraction, system=_SYSTEM, event_sink=event_sink
    )

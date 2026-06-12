"""extract_fnol_fields (T-01) — FNOL text → typed fields + per-field confidence.

flash-lite via GeminiClient, schema-validated with one repair retry. Returns the
validated model plus call metadata for the decision log.
"""

from __future__ import annotations

from collections.abc import Mapping

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
# NOTE: `overall_completeness` and `missing_required` returned by the LLM are kept
# for observability ONLY. Routing uses `assess_completeness` below — the orchestrator
# disposes (thesis 1/2), the LLM does not score its own gate.

# Canonical intake facts that gate completeness: who is covered (policy), when
# (loss_date) and where (loss_location). Completeness is computed DETERMINISTICALLY
# from the presence of these (thesis 1/2: the orchestrator disposes; routing is
# deterministic over typed inputs) — never from the LLM's self-reported
# `overall_completeness`, which proved unreliable (it scored a fully-specified
# claim at 0.80, sending it to the info-request loop). `peril` is the classifier's
# job and `description` is the narrative itself, so neither gates completeness.
REQUIRED_INTAKE_FIELDS: tuple[str, ...] = ("policy_number", "loss_date", "loss_location")


def assess_completeness(fields: Mapping[str, str | None]) -> tuple[float, list[str]]:
    """Deterministic intake completeness over `REQUIRED_INTAKE_FIELDS`.

    Returns ``(completeness 0..1, missing_field_names)``. A field counts as present
    when it has a non-blank value; the missing list drives the W4 document request,
    so it names exactly the facts we still need from the claimant.
    """
    present = [f for f in REQUIRED_INTAKE_FIELDS if (fields.get(f) or "").strip()]
    missing = [f for f in REQUIRED_INTAKE_FIELDS if f not in present]
    return len(present) / len(REQUIRED_INTAKE_FIELDS), missing


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

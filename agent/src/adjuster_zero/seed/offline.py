"""Deterministic offline planner — lets `make demo` and the eval harness run the
real graph without a GEMINI_API_KEY (CI, local smoke). It derives plausible
extraction/classification from a scenario's text + ground-truth labels, mimicking
what the LLM would return. Production uses the real GeminiClient."""

from __future__ import annotations

from typing import Any

from ..llm import GeminiClient, TaskKind
from ..llm.client import EventSink, LLMCallMeta
from ..planner.schemas import (
    ClaimClassification,
    ClassAlt,
    ExtractedField,
    FnolExtraction,
    LetterDraft,
)
from .data import Scenario


def build_offline_outputs(s: Scenario) -> tuple[FnolExtraction, ClaimClassification]:
    gt = s.ground_truth
    peril = gt.get("peril", "other")
    severity = int(gt.get("severity", 2))

    if s.policy_number and s.loss_date:
        extraction = FnolExtraction(
            fields=[
                ExtractedField(name="policy_number", value=s.policy_number, confidence=0.99),
                ExtractedField(name="loss_date", value=s.loss_date, confidence=0.95),
                ExtractedField(name="loss_location", value="reported in FNOL", confidence=0.9),
                ExtractedField(name="peril", value=peril, confidence=0.96),
                ExtractedField(name="description", value=s.fnol_text[:60], confidence=0.92),
            ],
            missing_required=[],
            overall_completeness=1.0,
        )
        classification = ClaimClassification(
            line="auto", peril=peril, severity=severity, complexity="low",
            confidence=0.95, alternatives=[ClassAlt(label="collision", p=0.05)],
        )
    else:
        extraction = FnolExtraction(
            fields=[ExtractedField(name="description", value=s.fnol_text[:60], confidence=0.6)],
            missing_required=["policy_number", "loss_date", "loss_location"],
            overall_completeness=0.45,
        )
        classification = ClaimClassification(
            line="auto", peril=peril, severity=severity, complexity="med", confidence=0.6,
        )
    return extraction, classification


def _generic_outputs() -> tuple[FnolExtraction, ClaimClassification]:
    """Fallback when no scenario is bound (e.g. resuming a paused graph, where
    extract/classify are already checkpointed and won't re-run)."""
    extraction = FnolExtraction(
        fields=[ExtractedField(name="description", value="claim", confidence=0.9)],
        missing_required=[],
        overall_completeness=1.0,
    )
    classification = ClaimClassification(
        line="auto", peril="other", severity=2, complexity="med", confidence=0.9
    )
    return extraction, classification


class OfflineGeminiClient(GeminiClient):
    def __init__(self, scenario: Scenario | None = None) -> None:
        super().__init__(api_key="offline")
        self._extraction, self._classification = (
            build_offline_outputs(scenario) if scenario else _generic_outputs()
        )

    async def generate_structured(
        self,
        task: TaskKind,
        prompt: str,
        schema: type[Any],
        *,
        system: str | None = None,
        temperature: float = 0.0,
        images: list[tuple[bytes, str]] | None = None,
        event_sink: EventSink | None = None,
    ) -> tuple[Any, LLMCallMeta]:
        meta = LLMCallMeta(model="offline", tokens_in=150, tokens_out=60, latency_ms=5)
        if task == TaskKind.EXTRACT:
            return self._extraction, meta
        if task == TaskKind.NARRATIVE:
            from ..planner.narrative import NarrativeAssessment

            return NarrativeAssessment(plausible=True, coherence=0.9, reason="offline default"), meta
        if task == TaskKind.LETTER:
            letter = LetterDraft(
                subject="Regarding your claim",
                body=(
                    "Dear claimant, we have reviewed your claim. Based on the policy "
                    "facts on file, we are writing to inform you of our determination. "
                    "Please see the claim record for details and your options."
                ),
            )
            return letter, meta
        return self._classification, meta

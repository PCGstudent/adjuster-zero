"""Structured-output schemas for the planner LLM calls."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    name: str = Field(description="Field name, e.g. policy_number, loss_date, peril.")
    value: str | None = Field(description="Extracted value, or null if absent.")
    confidence: float = Field(ge=0, le=1, description="Per-field confidence 0..1.")


class FnolExtraction(BaseModel):
    """Output of extract_fnol_fields (T-01)."""

    fields: list[ExtractedField]
    missing_required: list[str] = Field(
        default_factory=list,
        description="Required fields that are absent/illegible (e.g. policy_number).",
    )
    overall_completeness: float = Field(
        ge=0, le=1, description="Fraction of required info present, 0..1."
    )


class ClassAlt(BaseModel):
    label: str
    p: float = Field(ge=0, le=1)


class ClaimClassification(BaseModel):
    """Output of claim_classifier (T-04)."""

    line: str = Field(description="auto | property | injury")
    peril: str = Field(description="glass | collision | hail | theft | water | fire | other")
    severity: int = Field(ge=1, le=5, description="1 trivial .. 5 catastrophic.")
    complexity: str = Field(description="low | med | high")
    injury_flag: bool = False
    attorney_flag: bool = False
    confidence: float = Field(ge=0, le=1)
    alternatives: list[ClassAlt] = Field(default_factory=list)


class LetterDraft(BaseModel):
    """A drafted customer letter (e.g. a denial). flash via GeminiClient."""

    subject: str
    body: str

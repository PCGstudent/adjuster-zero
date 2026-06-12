"""Planner (the LLM). Three jobs: extraction, classification, planning. Every
output is schema-validated data (thesis 1) — never a side effect. Phase 1 ships
extraction + classification; planning is a fixed W1 template in the executor."""

from .classify import classify_claim
from .coverage import CoverageDetermination, apply_citation_floor, determine_coverage
from .explain import Explanation, explain_claim
from .extract import REQUIRED_INTAKE_FIELDS, assess_completeness, extract_fnol_fields
from .letter import draft_letter
from .narrative import NarrativeAssessment, assess_narrative
from .schemas import ClaimClassification, ExtractedField, FnolExtraction, LetterDraft
from .tiebreak import TiebreakDecision, decide_tiebreak
from .vision import VisionFnol, describe_damage

__all__ = [
    "extract_fnol_fields",
    "assess_completeness",
    "REQUIRED_INTAKE_FIELDS",
    "classify_claim",
    "draft_letter",
    "determine_coverage",
    "apply_citation_floor",
    "decide_tiebreak",
    "assess_narrative",
    "explain_claim",
    "describe_damage",
    "CoverageDetermination",
    "TiebreakDecision",
    "NarrativeAssessment",
    "Explanation",
    "VisionFnol",
    "ClaimClassification",
    "ExtractedField",
    "FnolExtraction",
    "LetterDraft",
]

"""The Claim Aggregate — the agent's working memory.

Deliberately curated and capped (no chat-history sludge): this object, not a
transcript, is what gets serialized into planner prompts and into LangGraph
state. It is a projection of claim_events.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .states import ClaimState, Workflow


class PolicyStatus(StrEnum):
    ACTIVE = "active"
    LAPSED = "lapsed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class Extraction(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)
    completeness: float = 0.0


class ClassAlternative(BaseModel):
    label: str
    p: float


class Classification(BaseModel):
    line: str | None = None
    peril: str | None = None
    severity: int | None = None  # 1..5
    complexity: str | None = None  # low | med | high
    injury_flag: bool = False
    attorney_flag: bool = False
    confidence: float = 0.0
    alternatives: list[ClassAlternative] = Field(default_factory=list)


class Coverage(BaseModel):
    covered: bool | None = None
    confidence: float = 0.0
    applicable_coverage: str | None = None
    exclusions_triggered: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    rationale: str | None = None


class Financials(BaseModel):
    amount_est: float | None = None
    reserve: float = 0.0
    paid: float = 0.0


class ClaimAggregate(BaseModel):
    """Canonical claim working object. Serializable into graph state."""

    id: str
    state: ClaimState = ClaimState.RECEIVED
    workflow: Workflow | None = None
    rule_id: str | None = None
    config_version: int | None = None

    # raw FNOL
    fnol_text: str = ""
    document_ids: list[str] = Field(default_factory=list)
    claimant_id: str | None = None
    policy_number: str | None = None
    policy_id: str | None = None
    policy_status: PolicyStatus = PolicyStatus.UNKNOWN

    # planner outputs
    extraction: Extraction = Field(default_factory=Extraction)
    classification: Classification = Field(default_factory=Classification)

    # investigation outputs
    coverage: Coverage = Field(default_factory=Coverage)
    fraud_score: float = 0.0
    fraud_signals: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_hard_match: bool = False  # exact duplicate → R-00 (semantic does NOT)
    degraded: bool = False  # a fraud control is down → cap routing at W2

    financials: Financials = Field(default_factory=Financials)
    open_questions: list[str] = Field(default_factory=list)

    # bounded-autonomy counters (thesis 6)
    token_budget_used: int = 0
    replan_count: int = 0

    # terminal/escalation bookkeeping
    reason_code: str | None = None

    # run context (propagated into events for end-to-end tracing)
    trace_id: str | None = None

    @property
    def confidence(self) -> float:
        """Composite confidence surfaced on the queue: min of the determinative
        signals we have (extraction completeness proxy, classification, coverage)."""
        sigs = [self.classification.confidence]
        if self.coverage.covered is not None:
            sigs.append(self.coverage.confidence)
        return round(min(sigs), 2) if sigs else 0.0

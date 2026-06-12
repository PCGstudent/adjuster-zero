"""Pydantic in/out schemas for the Phase 1 tools.

The key safety object is ``PaymentAuthorization`` (thesis 4): it requires at
least one of ``policy_gate_ref`` / ``approval_ref``. ``PaymentExecuteArgs`` then
*requires* an authorization field — so a payment without a gate/approval ref is
unrepresentable, caught at construction (Pydantic), not by a runtime ``if``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ── T-02 policy_lookup ───────────────────────────────────────────────────────
class PolicyLookupArgs(BaseModel):
    policy_number: str


class PolicyCoverage(BaseModel):
    code: str
    limit: float
    deductible: float


class PolicyLookupResult(BaseModel):
    policy_id: str
    status: Literal["active", "lapsed", "cancelled"]
    holder: str
    effective_from: str
    effective_to: str
    coverages: list[PolicyCoverage] = Field(default_factory=list)
    endorsements: list[str] = Field(default_factory=list)
    match_confidence: float = 1.0


# ── T-03 coverage_check (rules-only stub in Phase 1; RAG in Phase 3) ─────────
class CoverageCheckArgs(BaseModel):
    policy_id: str
    peril: str
    loss_date: str
    fields: dict[str, Any] = Field(default_factory=dict)


class CoverageCheckResult(BaseModel):
    covered: bool
    confidence: float = Field(ge=0, le=1)
    applicable_coverage: str | None = None
    exclusions_triggered: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    rationale: str = ""


# ── T-09 repair_cost_estimator ───────────────────────────────────────────────
class DamageItem(BaseModel):
    part: str
    severity: str = "moderate"


class RepairCostArgs(BaseModel):
    line: str
    damage_items: list[DamageItem] = Field(default_factory=list)
    zip: str | None = None


class RepairLineItem(BaseModel):
    desc: str
    parts: float
    labor_hours: float
    rate: float
    total: float


class RepairCostResult(BaseModel):
    line_items: list[RepairLineItem] = Field(default_factory=list)
    total: float
    confidence: float = Field(ge=0, le=1)
    partial: bool = False


# ── T-12 reserve_set (T1, idempotent) ────────────────────────────────────────
class ReserveSetArgs(BaseModel):
    claim_id: str
    amount: float
    rationale: str
    idempotency_key: str


class ReserveSetResult(BaseModel):
    reserve_id: str
    previous_amount: float
    new_amount: float


# ── Structural payment gate ──────────────────────────────────────────────────
class PaymentAuthorization(BaseModel):
    """A payment may proceed only with a policy tier-0 gate ref (W1 STP) OR a
    human approval ref (W2+). At least one is REQUIRED — enforced here, so the
    invalid call cannot be constructed."""

    model_config = {"frozen": True}

    policy_gate_ref: str | None = None
    approval_ref: str | None = None

    @model_validator(mode="after")
    def _require_a_ref(self) -> PaymentAuthorization:
        if not self.policy_gate_ref and not self.approval_ref:
            raise ValueError(
                "PaymentAuthorization requires policy_gate_ref or approval_ref "
                "(payment without a gate is unrepresentable)"
            )
        return self


# ── T-13 payment_execute (T2, idempotent) ────────────────────────────────────
class PaymentExecuteArgs(BaseModel):
    claim_id: str
    payee_id: str
    amount: float = Field(gt=0)
    method: Literal["ACH", "check"] = "ACH"
    # Required: no default → an ungated payment cannot be built.
    authorization: PaymentAuthorization
    idempotency_key: str


class PaymentExecuteResult(BaseModel):
    payment_id: str
    status: Literal["settled", "rejected"]
    settled_at: str


# ── T-14 customer_comm_send (draft=T0, send=T2) ──────────────────────────────
class CommSendArgs(BaseModel):
    claim_id: str
    template_id: str
    merge_fields: dict[str, Any] = Field(default_factory=dict)
    channel: Literal["email"] = "email"
    mode: Literal["draft", "send"] = "draft"
    # Sending a customer comm is T2: requires authorization, like a payment.
    authorization: PaymentAuthorization | None = None

    @model_validator(mode="after")
    def _send_requires_auth(self) -> CommSendArgs:
        if self.mode == "send" and self.authorization is None:
            raise ValueError("customer_comm_send in 'send' mode requires authorization")
        return self


class CommSendResult(BaseModel):
    draft_id: str
    message_id: str | None = None
    rendered_preview: str
    sent: bool = False


# ── T-07 claim_history (T0, idempotent) ──────────────────────────────────────
class ClaimHistoryArgs(BaseModel):
    claimant_id: str


class PriorClaim(BaseModel):
    claim_id: str
    date: str
    peril: str
    paid: float


class ClaimHistoryResult(BaseModel):
    prior_claims: list[PriorClaim] = Field(default_factory=list)
    count_24m: int = 0
    first_seen: bool = True
    recent_coverage_increase: bool = False


# ── T-06 duplicate_claim_check (T0, idempotent; exact-match in Phase 2) ───────
class DuplicateCheckArgs(BaseModel):
    claim_id: str
    claimant_id: str
    narrative: str = ""
    peril: str = ""
    loss_date: str = ""


class SemanticMatch(BaseModel):
    claim_id: str
    similarity: float


class DuplicateCheckResult(BaseModel):
    exact_matches: list[str] = Field(default_factory=list)
    semantic_matches: list[SemanticMatch] = Field(default_factory=list)
    degraded: bool = False  # set if the vector index is unavailable (Phase 3)


# ── T-05 fraud_signal_scan (T0; rules-only in Phase 2) ───────────────────────
class FraudScanArgs(BaseModel):
    claim_id: str
    prior_count_24m: int = 0
    exact_duplicate: bool = False
    recent_coverage_increase: bool = False
    first_seen: bool = False
    narrative_similarity: float = 0.0  # Phase 3 semantic duplicate signal


class FraudSignal(BaseModel):
    code: str
    weight: float
    evidence: str


class FraudScanResult(BaseModel):
    score: float = Field(ge=0, le=1)
    signals: list[FraudSignal] = Field(default_factory=list)
    degraded: bool = False


# ── T-15 document_request_create (T1) ────────────────────────────────────────
class DocRequestArgs(BaseModel):
    claim_id: str
    doc_types: list[str]
    due_days: int = 14


class DocRequestResult(BaseModel):
    request_id: str
    portal_url: str
    expires_at: str


# ── T-18 escalate_to_human (T1, the universal exit) ──────────────────────────
class EscalateArgs(BaseModel):
    claim_id: str
    reason_code: str
    risk_tier: int = 1
    summary: str
    requested_action: dict[str, Any] | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class EscalateResult(BaseModel):
    task_id: str
    queue: str
    sla_at: str

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

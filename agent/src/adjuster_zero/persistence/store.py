"""The ClaimStore protocol and the decision record model."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..domain.aggregate import ClaimAggregate
from ..domain.events import ClaimEvent


class DecisionRecord(BaseModel):
    """A first-class agent decision (thesis 9): confidence, alternatives,
    citations, guardrail results, tokens, latency — not a log line."""

    claim_id: str
    decision_type: str  # classify | route | plan | tiebreak | action | extract
    model: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    guardrails: dict[str, Any] = Field(default_factory=dict)
    rule_id: str | None = None
    config_version: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    trace_id: str | None = None


class ApprovalRecord(BaseModel):
    """A pending human-approval task (blueprint Part 3 approval layer)."""

    id: str
    claim_id: str
    requested_action: dict[str, Any]
    risk_tier: int = 2
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = None
    sla_at: str | None = None


class ClaimStore(Protocol):
    async def upsert_claim(self, agg: ClaimAggregate) -> None: ...
    async def append_event(self, ev: ClaimEvent) -> None: ...
    async def commit_transition(self, agg: ClaimAggregate, ev: ClaimEvent) -> None:
        """Atomically write the event AND the claim projection (thesis 5: the
        event IS the transition — they must not diverge on a crash)."""
        ...
    async def record_decision(self, dec: DecisionRecord) -> None: ...
    async def record_tool_call(self, record: dict[str, Any]) -> None: ...
    async def start_execution(
        self, exec_id: str, claim_id: str, workflow: str | None, engine_ref: str | None
    ) -> None: ...
    async def update_execution(self, exec_id: str, **fields: Any) -> None: ...

    # reads (dashboard)
    async def list_claims(self) -> list[dict[str, Any]]: ...
    async def get_claim(self, claim_id: str) -> dict[str, Any] | None: ...
    async def get_events(self, claim_id: str) -> list[dict[str, Any]]: ...
    async def get_decisions(self, claim_id: str) -> list[dict[str, Any]]: ...
    async def get_tool_calls(self, claim_id: str) -> list[dict[str, Any]]: ...
    async def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]: ...

    # analytics reads
    async def list_all_approvals(self) -> list[dict[str, Any]]: ...
    async def all_tool_calls(self) -> list[dict[str, Any]]: ...
    async def all_decisions(self) -> list[dict[str, Any]]: ...

    # contact-agent leads
    async def create_lead(self, lead: dict[str, Any]) -> None: ...
    async def list_leads(self) -> list[dict[str, Any]]: ...

    # approvals (HITL)
    async def create_approval(self, appr: ApprovalRecord) -> None: ...
    async def get_approval(self, approval_id: str) -> dict[str, Any] | None: ...
    async def list_pending_approvals(self) -> list[dict[str, Any]]: ...
    async def resolve_approval(
        self,
        approval_id: str,
        *,
        resolution: str,
        delta: dict[str, Any] | None,
        reason_code: str | None,
        resolved_by: str | None,
    ) -> None: ...

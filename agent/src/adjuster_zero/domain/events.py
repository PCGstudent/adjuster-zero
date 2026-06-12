"""The versioned event envelope and canonical event types.

Every state transition and every tool call writes one of these to claim_events.
The dashboard consumes them via Supabase Realtime; the aggregate is a
projection of them. (Blueprint Part 3 event envelope.)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    # lifecycle
    RECEIVED = "claim.received"
    EXTRACTED = "claim.extracted"
    CLASSIFIED = "claim.classified"
    INVESTIGATED = "claim.investigated"
    ROUTED = "claim.routed"
    PLAN_CREATED = "claim.plan_created"
    EXECUTING = "claim.executing"
    SETTLED = "claim.settled"
    CLOSED = "claim.closed"
    PARKED = "claim.parked"
    DOCUMENT_RECEIVED = "claim.document_received"
    DENIED = "claim.denied"
    ESCALATED = "claim.escalated"
    FAILED = "claim.failed"
    COMPENSATED = "claim.compensated"
    # tools & decisions
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    DECISION = "agent.decision"
    # approvals (Phase 2)
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    APPROVAL_SLA_BREACH = "approval.sla_breach"
    # timers (pg_cron)
    REMINDER = "claim.reminder"
    # control / observability
    BUDGET_EXHAUSTED = "claim.budget_exhausted"
    REPLAN_LIMIT = "claim.replan_limit"
    RATE_LIMITED = "llm.rate_limited"
    DOWNGRADED = "llm.downgraded"
    SCHEMA_REPAIR = "llm.schema_repair"
    DEGRADED_MODE = "control.degraded_mode"


class EventActor(BaseModel):
    kind: str = "agent"  # agent | human | system
    component: str | None = None  # e.g. "router", "executor", "planner"
    user_id: str | None = None


class ClaimEvent(BaseModel):
    claim_id: str
    type: EventType
    v: int = 1
    actor: EventActor = Field(default_factory=EventActor)
    data: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


def claim_event(
    claim_id: str,
    type: EventType,
    *,
    component: str | None = None,
    actor_kind: str = "agent",
    user_id: str | None = None,
    data: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> ClaimEvent:
    return ClaimEvent(
        claim_id=claim_id,
        type=type,
        actor=EventActor(kind=actor_kind, component=component, user_id=user_id),
        data=data or {},
        trace_id=trace_id,
    )

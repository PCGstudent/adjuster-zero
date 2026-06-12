"""Claim lifecycle states and workflow identifiers.

States mirror the DB CHECK constraint in 001_init.sql and the blueprint state
machine. Workflows are the five routing targets W1..W5.
"""

from __future__ import annotations

from enum import StrEnum


class ClaimState(StrEnum):
    RECEIVED = "RECEIVED"
    TRIAGE = "TRIAGE"
    INFO_PENDING = "INFO_PENDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    REVIEW_PENDING = "REVIEW_PENDING"
    SETTLEMENT = "SETTLEMENT"
    CLOSED = "CLOSED"
    DENIED = "DENIED"
    WITHDRAWN = "WITHDRAWN"
    ESCALATED = "ESCALATED"


# Terminal states: no further transitions.
TERMINAL_STATES = frozenset(
    {ClaimState.CLOSED, ClaimState.DENIED, ClaimState.WITHDRAWN, ClaimState.ESCALATED}
)


class Workflow(StrEnum):
    W1 = "W1"  # Straight-through processing
    W2 = "W2"  # Standard adjudication (human approval)
    W3 = "W3"  # Fraud investigation (SIU) — no payment edge
    W4 = "W4"  # Information request loop
    W5 = "W5"  # High-severity escalation

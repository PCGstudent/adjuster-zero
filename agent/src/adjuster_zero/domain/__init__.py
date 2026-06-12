"""Domain layer: the claim aggregate, the event envelope, and event types.

The aggregate is the agent's working memory (a curated, capped projection of the
event log), serialized into LangGraph state. The event IS the state transition
(thesis 5): nothing mutates a claim without emitting the corresponding event.
"""

from .aggregate import (
    ClaimAggregate,
    Classification,
    Coverage,
    Extraction,
    Financials,
    PolicyStatus,
)
from .events import EventActor, EventType, claim_event
from .states import ClaimState, Workflow

__all__ = [
    "ClaimAggregate",
    "Classification",
    "Coverage",
    "Extraction",
    "Financials",
    "PolicyStatus",
    "EventActor",
    "EventType",
    "claim_event",
    "ClaimState",
    "Workflow",
]

"""Per-workflow tool allow-lists.

The executor rejects any plan step whose tool is not allowed for the routed
workflow. This is the second, independent guarantee (alongside the state machine)
that **no payment edge is reachable from W2/W3/W4/W5**: payment_execute appears
only in W1's allow-list. Tested in test_tools.py.
"""

from __future__ import annotations

from ..domain.states import Workflow

# Phase 1 tool set. Later phases extend these lists (fraud_signal_scan,
# document_request_create, escalate_to_human, etc.).
_READ_ONLY = {"policy_lookup", "coverage_check", "repair_cost_estimator"}

WORKFLOW_ALLOWLISTS: dict[Workflow, frozenset[str]] = {
    # W1 STP — the ONLY workflow that may execute a payment.
    Workflow.W1: frozenset(_READ_ONLY | {"reserve_set", "payment_execute", "customer_comm_send"}),
    # W2 standard adjudication — investigate, reserve, draft comms; pay only after
    # human approval (Phase 2 adds approval_ref-gated payment back via the gate).
    Workflow.W2: frozenset(_READ_ONLY | {"reserve_set", "customer_comm_send"}),
    # W3 fraud — read-only analysis only; NO reserve, NO payment, NO send.
    Workflow.W3: frozenset(_READ_ONLY),
    # W4 information request — gather + request documents + draft comms.
    Workflow.W4: frozenset(_READ_ONLY | {"customer_comm_send"}),
    # W5 high-severity escalation — read-only; a human adjuster owns it.
    Workflow.W5: frozenset(_READ_ONLY | {"customer_comm_send"}),
}


def tool_allowed(workflow: Workflow, tool_name: str) -> bool:
    return tool_name in WORKFLOW_ALLOWLISTS.get(workflow, frozenset())

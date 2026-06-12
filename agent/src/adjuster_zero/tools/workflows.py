"""Per-workflow tool allow-lists.

The executor rejects any plan step whose tool is not allowed for the routed
workflow. This is the second, independent guarantee (alongside the state machine)
that **no payment edge is reachable from W2/W3/W4/W5**: payment_execute appears
only in W1's allow-list. Tested in test_tools.py.
"""

from __future__ import annotations

from ..domain.states import Workflow

# Read-only (T0) investigation tools — allowed in every workflow (and during
# pre-routing triage via the executor's workflow=None path).
_READ_ONLY = {
    "policy_lookup", "coverage_check", "repair_cost_estimator",
    "claim_history", "duplicate_claim_check", "fraud_signal_scan",
    "weather_event_verify", "guideline_search", "sanctions_watchlist_check",
}

WORKFLOW_ALLOWLISTS: dict[Workflow, frozenset[str]] = {
    # W1 STP — pays via the tier-0 policy gate (policy_gate_ref).
    Workflow.W1: frozenset(_READ_ONLY | {"reserve_set", "payment_execute", "customer_comm_send"}),
    # W2 standard adjudication — pays ONLY after human approval (approval_ref).
    # payment_execute is allowed here, but PaymentAuthorization makes an ungated
    # call unrepresentable and the graph only builds an approval_ref post-approval.
    Workflow.W2: frozenset(
        _READ_ONLY | {"reserve_set", "payment_execute", "customer_comm_send", "escalate_to_human"}
    ),
    # W3 fraud — read-only analysis + escalate ONLY. NO reserve/payment/send:
    # no payment edge is reachable from W3, by allow-list (and by graph topology).
    Workflow.W3: frozenset(_READ_ONLY | {"escalate_to_human"}),
    # W4 information request — gather, request documents, draft comms, escalate.
    Workflow.W4: frozenset(
        _READ_ONLY | {"customer_comm_send", "document_request_create", "escalate_to_human"}
    ),
    # W5 high-severity escalation — read-only + draft comms + escalate to a human.
    Workflow.W5: frozenset(_READ_ONLY | {"customer_comm_send", "escalate_to_human"}),
}


def tool_allowed(workflow: Workflow, tool_name: str) -> bool:
    return tool_name in WORKFLOW_ALLOWLISTS.get(workflow, frozenset())

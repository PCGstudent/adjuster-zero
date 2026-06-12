"""Tool-layer tests (Phase 1 acceptance):
  * payment_execute cannot be constructed without a gate/approval ref
    (compile/validation-level structural test, thesis 4)
  * payment idempotency (exactly-once via key, reconcile-before-retry)
  * no payment edge reachable from W2/W3/W4/W5 (allow-list test)
  * arg validation rejects malformed calls
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from adjuster_zero.domain.states import Workflow
from adjuster_zero.tools import ToolExecutor, build_registry
from adjuster_zero.tools.executor import ToolArgInvalid, ToolNotAllowed
from adjuster_zero.tools.schemas import PaymentAuthorization, PaymentExecuteArgs


# ── Structural payment gate (thesis 4) ───────────────────────────────────────
def test_payment_authorization_requires_a_ref() -> None:
    with pytest.raises(ValidationError):
        PaymentAuthorization()  # neither ref → unrepresentable
    assert PaymentAuthorization(policy_gate_ref="W1-T0-ceiling-2500").policy_gate_ref
    assert PaymentAuthorization(approval_ref="appr_123").approval_ref


def test_payment_args_require_authorization() -> None:
    with pytest.raises(ValidationError):
        # No authorization field → cannot be constructed.
        PaymentExecuteArgs(
            claim_id="CLM-1", payee_id="CLMT-001", amount=412, idempotency_key="k1"
        )  # type: ignore[call-arg]
    # With a gate ref it constructs fine.
    ok = PaymentExecuteArgs(
        claim_id="CLM-1",
        payee_id="CLMT-001",
        amount=412,
        idempotency_key="k1",
        authorization=PaymentAuthorization(policy_gate_ref="W1-T0-ceiling-2500"),
    )
    assert ok.authorization.policy_gate_ref == "W1-T0-ceiling-2500"


def _pay_args(key: str = "CLM-1-pay-1") -> PaymentExecuteArgs:
    return PaymentExecuteArgs(
        claim_id="CLM-1",
        payee_id="CLMT-001",
        amount=412,
        idempotency_key=key,
        authorization=PaymentAuthorization(policy_gate_ref="W1-T0-ceiling-2500"),
    )


# ── No payment edge reachable from fraud / info / high-severity (allow-list) ──
# W1 pays via the tier-0 gate; W2 pays only after human approval (approval_ref).
# W3/W4/W5 have NO payment edge — structurally rejected by the executor.
@pytest.mark.parametrize("wf", [Workflow.W3, Workflow.W4, Workflow.W5])
def test_payment_unreachable_from_w3_w4_w5(wf: Workflow) -> None:
    ex = ToolExecutor(build_registry())

    async def run() -> None:
        with pytest.raises(ToolNotAllowed):
            await ex.execute(wf, "payment_execute", _pay_args(), claim_id="CLM-1")

    asyncio.run(run())


def test_payment_allowed_on_w1_and_w2() -> None:
    ex = ToolExecutor(build_registry())

    async def run() -> None:
        for wf in (Workflow.W1, Workflow.W2):
            res = await ex.execute(wf, "payment_execute", _pay_args(f"k-{wf}"), claim_id="CLM-1")
            assert res.ok and res.data["status"] == "settled"

    asyncio.run(run())


# ── Idempotency / reconcile-before-retry ─────────────────────────────────────
def test_payment_idempotent_same_key_settles_once() -> None:
    ex = ToolExecutor(build_registry())

    async def run() -> None:
        r1 = await ex.execute(Workflow.W1, "payment_execute", _pay_args(), claim_id="CLM-1")
        r2 = await ex.execute(Workflow.W1, "payment_execute", _pay_args(), claim_id="CLM-1")
        assert r1.ok and r2.ok
        assert r1.cached is False and r2.cached is True
        assert r1.data["payment_id"] == r2.data["payment_id"]

    asyncio.run(run())


def test_reserve_idempotent() -> None:
    ex = ToolExecutor(build_registry())

    async def run() -> None:
        args = {
            "claim_id": "CLM-1",
            "amount": 450,
            "rationale": "glass repair estimate",
            "idempotency_key": "CLM-1-rsv-1",
        }
        r1 = await ex.execute(Workflow.W1, "reserve_set", args, claim_id="CLM-1")
        r2 = await ex.execute(Workflow.W1, "reserve_set", args, claim_id="CLM-1")
        assert r1.data["reserve_id"] == r2.data["reserve_id"]
        assert r2.cached is True

    asyncio.run(run())


# ── Arg validation ───────────────────────────────────────────────────────────
def test_invalid_args_escalate() -> None:
    ex = ToolExecutor(build_registry())

    async def run() -> None:
        with pytest.raises(ToolArgInvalid):
            await ex.execute(Workflow.W1, "policy_lookup", {"wrong": "x"}, claim_id="CLM-1")

    asyncio.run(run())


# ── Read-only tools work and record ──────────────────────────────────────────
def test_policy_lookup_and_coverage_clean_glass() -> None:
    ex = ToolExecutor(build_registry())

    async def run() -> None:
        pol = await ex.execute(
            Workflow.W1, "policy_lookup", {"policy_number": "POL-88341"}, claim_id="CLM-1"
        )
        assert pol.ok and pol.data["status"] == "active"
        cov = await ex.execute(
            Workflow.W1,
            "coverage_check",
            {"policy_id": "pol_88341", "peril": "glass", "loss_date": "2026-06-08"},
            claim_id="CLM-1",
        )
        assert cov.ok and cov.data["covered"] is True

    asyncio.run(run())


def test_ambiguous_handler_exception_is_safe_failure_not_crash() -> None:
    """A non-ToolFailure handler error (e.g. timeout) must become a NON-retryable
    failure envelope, not propagate — and must NOT be cached (no blind retry)."""
    registry = build_registry()

    async def boom(_args):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated ACH timeout")

    registry["payment_execute"].handler = boom
    ex = ToolExecutor(registry)

    async def run() -> None:
        res = await ex.execute(Workflow.W1, "payment_execute", _pay_args("k-timeout"), claim_id="CLM-1")
        assert res.ok is False
        assert res.error is not None and res.error.code == "TOOL_ERROR"
        assert res.error.retryable is False
        # The failed side effect was NOT cached as a success.
        assert await ex.idempotency.get("k-timeout") is None

    asyncio.run(run())


def test_coverage_lapsed_not_covered() -> None:
    ex = ToolExecutor(build_registry())

    async def run() -> None:
        cov = await ex.execute(
            Workflow.W2,
            "coverage_check",
            {"policy_id": "pol_77120", "peril": "glass", "loss_date": "2026-06-08"},
            claim_id="CLM-2",
        )
        assert cov.ok and cov.data["covered"] is False
        assert "POLICY_INACTIVE" in cov.data["exclusions_triggered"]

    asyncio.run(run())

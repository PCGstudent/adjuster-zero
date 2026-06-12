"""Builds the tool registry: name → Tool (schemas, risk tier, idempotent, handler)."""

from __future__ import annotations

from . import handlers
from .base import RiskTier, Tool
from .schemas import (
    CommSendArgs,
    CommSendResult,
    CoverageCheckArgs,
    CoverageCheckResult,
    PaymentExecuteArgs,
    PaymentExecuteResult,
    PolicyLookupArgs,
    PolicyLookupResult,
    RepairCostArgs,
    RepairCostResult,
    ReserveSetArgs,
    ReserveSetResult,
)


def build_registry() -> dict[str, Tool]:
    tools: list[Tool] = [
        Tool(
            name="policy_lookup",
            description="Fetch the policy record from the policy-admin system (mock).",
            args_schema=PolicyLookupArgs,
            result_schema=PolicyLookupResult,
            risk_tier=RiskTier.T0,
            idempotent=True,
            handler=handlers.policy_lookup,
        ),
        Tool(
            name="coverage_check",
            description="Determine whether the loss is covered (rules-only stub in Phase 1).",
            args_schema=CoverageCheckArgs,
            result_schema=CoverageCheckResult,
            risk_tier=RiskTier.T0,
            idempotent=False,
            handler=handlers.coverage_check,
        ),
        Tool(
            name="repair_cost_estimator",
            description="Line-item repair estimate from a parts/labor table (mock).",
            args_schema=RepairCostArgs,
            result_schema=RepairCostResult,
            risk_tier=RiskTier.T0,
            idempotent=True,
            handler=handlers.repair_cost_estimator,
        ),
        Tool(
            name="reserve_set",
            description="Set/adjust the financial reserve (T1, idempotent via key).",
            args_schema=ReserveSetArgs,
            result_schema=ReserveSetResult,
            risk_tier=RiskTier.T1,
            idempotent=True,
            handler=handlers.reserve_set,
        ),
        Tool(
            name="payment_execute",
            description="Disburse settlement via mock ACH (T2; requires authorization).",
            args_schema=PaymentExecuteArgs,
            result_schema=PaymentExecuteResult,
            risk_tier=RiskTier.T2,
            idempotent=True,
            handler=handlers.payment_execute,
        ),
        Tool(
            name="customer_comm_send",
            description="Draft (T0) or send (T2) a templated claimant communication.",
            args_schema=CommSendArgs,
            result_schema=CommSendResult,
            risk_tier=RiskTier.T2,
            idempotent=False,
            handler=handlers.customer_comm_send,
        ),
    ]
    return {t.name: t for t in tools}

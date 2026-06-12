"""In-memory ClaimStore — used by tests and for local runs without Supabase."""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..domain.aggregate import ClaimAggregate
from ..domain.events import ClaimEvent
from .store import ApprovalRecord, DecisionRecord


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


class InMemoryClaimStore:
    def __init__(self) -> None:
        self.claims: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.executions: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self._seq = 0

    async def upsert_claim(self, agg: ClaimAggregate) -> None:
        self.claims[agg.id] = {
            "id": agg.id,
            "state": agg.state.value,
            "workflow": agg.workflow.value if agg.workflow else None,
            "line": agg.classification.line,
            "peril": agg.classification.peril,
            "severity": agg.classification.severity,
            "fraud_score": agg.fraud_score,
            "confidence": agg.confidence,
            "completeness": agg.extraction.completeness,
            "amount_est": agg.financials.amount_est,
            "reserve": agg.financials.reserve,
            "paid": agg.financials.paid,
            "claimant_id": agg.claimant_id,
            "policy_id": agg.policy_id,
            "rule_id": agg.rule_id,
            "reason_code": agg.reason_code,
            "updated_at": _now(),
        }

    async def append_event(self, ev: ClaimEvent) -> None:
        self._seq += 1
        self.events.append({"seq": self._seq, "ts": _now(), **ev.model_dump(mode="json")})

    async def commit_transition(self, agg: ClaimAggregate, ev: ClaimEvent) -> None:
        # In-process: the two writes can't interleave with a crash mid-pair.
        await self.upsert_claim(agg)
        await self.append_event(ev)

    async def record_decision(self, dec: DecisionRecord) -> None:
        self.decisions.append({"ts": _now(), **dec.model_dump(mode="json")})

    async def record_tool_call(self, record: dict[str, Any]) -> None:
        self.tool_calls.append({"ts": _now(), **record})

    async def start_execution(
        self, exec_id: str, claim_id: str, workflow: str | None, engine_ref: str | None
    ) -> None:
        self.executions[exec_id] = {
            "exec_id": exec_id,
            "claim_id": claim_id,
            "workflow": workflow,
            "engine_ref": engine_ref,
            "status": "running",
            "started_at": _now(),
            "replan_count": 0,
            "token_budget_used": 0,
        }

    async def update_execution(self, exec_id: str, **fields: Any) -> None:
        self.executions.setdefault(exec_id, {"exec_id": exec_id}).update(fields)

    async def list_claims(self) -> list[dict[str, Any]]:
        return sorted(self.claims.values(), key=lambda c: c["updated_at"], reverse=True)

    async def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        return self.claims.get(claim_id)

    async def get_events(self, claim_id: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["claim_id"] == claim_id]

    async def get_decisions(self, claim_id: str) -> list[dict[str, Any]]:
        return [d for d in self.decisions if d["claim_id"] == claim_id]

    async def get_tool_calls(self, claim_id: str) -> list[dict[str, Any]]:
        return [t for t in self.tool_calls if t.get("claim_id") == claim_id]

    async def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self.events[-limit:]))

    async def create_approval(self, appr: ApprovalRecord) -> None:
        self.approvals[appr.id] = {
            **appr.model_dump(),
            "status": "pending",
            "resolution": None,
            "delta": None,
            "reason_code": None,
            "resolved_by": None,
            "created_at": _now(),
            "resolved_at": None,
        }

    async def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        return self.approvals.get(approval_id)

    async def list_pending_approvals(self) -> list[dict[str, Any]]:
        return [a for a in self.approvals.values() if a["status"] == "pending"]

    async def resolve_approval(
        self, approval_id: str, *, resolution: str, delta: dict[str, Any] | None,
        reason_code: str | None, resolved_by: str | None,
    ) -> None:
        a = self.approvals.get(approval_id)
        if a is None:
            return
        status = {"approve": "approved", "modify": "modified", "reject": "rejected"}[resolution]
        a.update({
            "status": status, "resolution": resolution, "delta": delta,
            "reason_code": reason_code, "resolved_by": resolved_by, "resolved_at": _now(),
        })

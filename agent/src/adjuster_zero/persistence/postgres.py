"""PostgresClaimStore — the Supabase-backed ClaimStore.

Writes the claim projection, the event log, decisions, tool calls, and workflow
executions. The agent connects with the service-role DATABASE_URL (bypasses RLS).
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from .. import db
from ..domain.aggregate import ClaimAggregate
from ..domain.events import ClaimEvent
from .store import ApprovalRecord, DecisionRecord


class PostgresIdempotencyStore:
    """Reconcile-before-retry backed by tool_calls.idempotency_key (UNIQUE).

    A side-effecting tool with a previously-seen key returns the persisted prior
    result instead of acting again — and this survives an agent-service restart,
    unlike an in-memory store. ``put`` is a no-op: record_tool_call persists the
    row that ``get`` later finds."""

    async def get(self, key: str) -> dict[str, Any] | None:
        pool = db.get_pool()
        if pool is None:
            return None
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT result FROM tool_calls WHERE idempotency_key = %s AND status = 'ok' LIMIT 1",
                (key,),
            )
            row = await cur.fetchone()
            return row["result"] if row else None

    async def put(self, key: str, value: dict[str, Any]) -> None:
        return None  # persistence happens via record_tool_call's INSERT


class PostgresClaimStore:
    @staticmethod
    def _upsert_sql() -> str:
        return """
            INSERT INTO claims (id, state, workflow, line, peril, severity,
                fraud_score, confidence, completeness, amount_est, reserve, paid,
                claimant_id, policy_id, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                state=EXCLUDED.state, workflow=EXCLUDED.workflow, line=EXCLUDED.line,
                peril=EXCLUDED.peril, severity=EXCLUDED.severity,
                fraud_score=EXCLUDED.fraud_score, confidence=EXCLUDED.confidence,
                completeness=EXCLUDED.completeness, amount_est=EXCLUDED.amount_est,
                reserve=EXCLUDED.reserve, paid=EXCLUDED.paid,
                claimant_id=EXCLUDED.claimant_id, policy_id=EXCLUDED.policy_id,
                version=claims.version+1, updated_at=now()
        """

    @staticmethod
    def _upsert_params(agg: ClaimAggregate) -> tuple[Any, ...]:
        return (
            agg.id, agg.state.value, agg.workflow.value if agg.workflow else None,
            agg.classification.line, agg.classification.peril, agg.classification.severity,
            agg.fraud_score, agg.confidence, agg.extraction.completeness,
            agg.financials.amount_est, agg.financials.reserve, agg.financials.paid,
            agg.claimant_id, agg.policy_id,
        )

    @staticmethod
    def _event_params(ev: ClaimEvent) -> tuple[Any, ...]:
        return (ev.claim_id, ev.type.value, ev.v, Json(ev.actor.model_dump()),
                Json(ev.data), ev.trace_id)

    _EVENT_SQL = (
        "INSERT INTO claim_events (claim_id, type, v, actor, data, trace_id) "
        "VALUES (%s,%s,%s,%s,%s,%s)"
    )

    async def commit_transition(self, agg: ClaimAggregate, ev: ClaimEvent) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        async with pool.connection() as conn:
            async with conn.transaction(), conn.cursor() as cur:
                await cur.execute(self._upsert_sql(), self._upsert_params(agg))
                await cur.execute(self._EVENT_SQL, self._event_params(ev))

    async def upsert_claim(self, agg: ClaimAggregate) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO claims (id, state, workflow, line, peril, severity,
                    fraud_score, confidence, completeness, amount_est, reserve, paid,
                    claimant_id, policy_id, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (id) DO UPDATE SET
                    state=EXCLUDED.state, workflow=EXCLUDED.workflow, line=EXCLUDED.line,
                    peril=EXCLUDED.peril, severity=EXCLUDED.severity,
                    fraud_score=EXCLUDED.fraud_score, confidence=EXCLUDED.confidence,
                    completeness=EXCLUDED.completeness, amount_est=EXCLUDED.amount_est,
                    reserve=EXCLUDED.reserve, paid=EXCLUDED.paid,
                    claimant_id=EXCLUDED.claimant_id, policy_id=EXCLUDED.policy_id,
                    version=claims.version+1, updated_at=now()
                """,
                (
                    agg.id, agg.state.value, agg.workflow.value if agg.workflow else None,
                    agg.classification.line, agg.classification.peril, agg.classification.severity,
                    agg.fraud_score, agg.confidence, agg.extraction.completeness,
                    agg.financials.amount_est, agg.financials.reserve, agg.financials.paid,
                    agg.claimant_id, agg.policy_id,
                ),
            )

    async def append_event(self, ev: ClaimEvent) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO claim_events (claim_id, type, v, actor, data, trace_id) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (ev.claim_id, ev.type.value, ev.v, Json(ev.actor.model_dump()),
                 Json(ev.data), ev.trace_id),
            )

    async def record_decision(self, dec: DecisionRecord) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO agent_decisions (claim_id, decision_type, model, output,
                    confidence, alternatives, citations, guardrails, rule_id,
                    config_version, tokens_in, tokens_out, latency_ms, trace_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (dec.claim_id, dec.decision_type, dec.model, Json(dec.output),
                 dec.confidence, Json(dec.alternatives), Json(dec.citations),
                 Json(dec.guardrails), dec.rule_id, dec.config_version,
                 dec.tokens_in, dec.tokens_out, dec.latency_ms, dec.trace_id),
            )

    async def record_tool_call(self, r: dict[str, Any]) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        # Only a SUCCESSFUL side effect claims the unique idempotency slot. A
        # failed/ambiguous attempt records with a null key so it neither blocks a
        # later successful retry from recording nor is mistaken for a settled
        # payment by the reconcile lookup (which filters status='ok').
        idem = r.get("idempotency_key") if r["status"] == "ok" else None
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO tool_calls (claim_id, exec_id, seq, tool, risk_tier, args,
                    args_hash, idempotency_key, status, result, error_code, latency_ms, cached)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                (r["claim_id"], r.get("exec_id"), r.get("seq", 0), r["tool"], r["risk_tier"],
                 Json(r.get("args")), r.get("args_hash"), idem,
                 r["status"], Json(r.get("result")), r.get("error_code"),
                 r.get("latency_ms", 0), r.get("cached", False)),
            )

    async def start_execution(
        self, exec_id: str, claim_id: str, workflow: str | None, engine_ref: str | None
    ) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO workflow_executions (exec_id, claim_id, workflow, engine_ref, status) "
                "VALUES (%s,%s,%s,%s,'running') ON CONFLICT (exec_id) DO NOTHING",
                (exec_id, claim_id, workflow, engine_ref),
            )

    async def update_execution(self, exec_id: str, **fields: Any) -> None:
        pool = db.get_pool()
        if pool is None or not fields:
            return
        cols = ", ".join(f"{k} = %s" for k in fields)
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"UPDATE workflow_executions SET {cols} WHERE exec_id = %s",
                (*fields.values(), exec_id),
            )

    async def _query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        pool = db.get_pool()
        if pool is None:
            return []
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            return list(await cur.fetchall())

    async def list_claims(self) -> list[dict[str, Any]]:
        return await self._query("SELECT * FROM claims ORDER BY updated_at DESC LIMIT 200")

    async def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        rows = await self._query("SELECT * FROM claims WHERE id = %s", (claim_id,))
        return rows[0] if rows else None

    async def get_events(self, claim_id: str) -> list[dict[str, Any]]:
        return await self._query(
            "SELECT id, ts, type, actor, data, trace_id FROM claim_events "
            "WHERE claim_id = %s ORDER BY ts, id",
            (claim_id,),
        )

    async def get_decisions(self, claim_id: str) -> list[dict[str, Any]]:
        return await self._query(
            "SELECT * FROM agent_decisions WHERE claim_id = %s ORDER BY ts", (claim_id,)
        )

    async def get_tool_calls(self, claim_id: str) -> list[dict[str, Any]]:
        return await self._query(
            "SELECT * FROM tool_calls WHERE claim_id = %s ORDER BY ts", (claim_id,)
        )

    async def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._query(
            "SELECT id, claim_id, ts, type, actor, data, trace_id FROM claim_events "
            "ORDER BY ts DESC, id DESC LIMIT %s",
            (limit,),
        )

    async def list_all_approvals(self) -> list[dict[str, Any]]:
        return await self._query("SELECT * FROM approvals ORDER BY created_at DESC LIMIT 500")

    async def all_tool_calls(self) -> list[dict[str, Any]]:
        return await self._query(
            "SELECT tool, status, error_code FROM tool_calls ORDER BY ts DESC LIMIT 2000")

    async def all_decisions(self) -> list[dict[str, Any]]:
        return await self._query(
            "SELECT decision_type, guardrails FROM agent_decisions ORDER BY ts DESC LIMIT 2000")

    async def create_lead(self, lead: dict[str, Any]) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO leads (name, email, message, process, qualified, "
                "clarifying_question, email_draft, trace_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (lead.get("name"), lead.get("email"), lead.get("message"), lead.get("process"),
                 lead.get("qualified"), lead.get("clarifying_question"),
                 lead.get("email_draft"), lead.get("trace_id")),
            )

    async def list_leads(self) -> list[dict[str, Any]]:
        return await self._query("SELECT * FROM leads ORDER BY ts DESC LIMIT 200")

    async def create_approval(self, appr: ApprovalRecord) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO approvals (id, claim_id, requested_action, risk_tier,
                    evidence_refs, confidence, status, sla_at)
                VALUES (%s,%s,%s,%s,%s,%s,'pending',%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (appr.id, appr.claim_id, Json(appr.requested_action), appr.risk_tier,
                 Json(appr.evidence_refs), appr.confidence, appr.sla_at),
            )

    async def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = await self._query("SELECT * FROM approvals WHERE id = %s", (approval_id,))
        return rows[0] if rows else None

    async def list_pending_approvals(self) -> list[dict[str, Any]]:
        return await self._query(
            "SELECT * FROM approvals WHERE status = 'pending' ORDER BY sla_at NULLS LAST, created_at"
        )

    async def resolve_approval(
        self, approval_id: str, *, resolution: str, delta: dict[str, Any] | None,
        reason_code: str | None, resolved_by: str | None,
    ) -> None:
        pool = db.get_pool()
        if pool is None:
            return
        status = {"approve": "approved", "modify": "modified", "reject": "rejected"}[resolution]
        # resolved_by is a users.id UUID FK; without seeded auth users we leave it
        # NULL (the resolution + reason_code capture the human action for calibration).
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE approvals SET status=%s, resolution=%s, delta=%s, reason_code=%s,
                    resolved_at=now()
                WHERE id=%s
                """,
                (status, resolution, Json(delta), reason_code, approval_id),
            )

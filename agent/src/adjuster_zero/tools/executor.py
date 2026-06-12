"""The tool executor: the orchestrator's hands.

Per blueprint Part 4 it validates args against the schema *before* invoke and the
result *after*, enforces the routed workflow's allow-list, enforces idempotency
(reconcile-before-retry for side-effecting tools), and returns the uniform
envelope. It never runs a framework auto tool-calling loop — the caller (the
LangGraph executor node) decides what to call.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from ..domain.states import Workflow
from ..llm.errors import EscalateToHuman
from .base import RiskTier, Tool, ToolFailure, ToolResult
from .workflows import tool_allowed

# A recorder persists a tool-call row (a first-class tool_calls entity). The
# dashboard timeline merges tool_calls with claim_events; both stream via Realtime.
ToolRecorder = Callable[[dict[str, Any]], Awaitable[None]]


class ToolNotAllowed(EscalateToHuman):
    def __init__(self, workflow: Workflow | None, tool: str) -> None:
        where = workflow.value if workflow else "triage (read-only)"
        super().__init__(
            "TOOL_NOT_ALLOWED",
            f"Tool '{tool}' is not in the allow-list for {where}",
        )


class ToolArgInvalid(EscalateToHuman):
    def __init__(self, tool: str, errors: str) -> None:
        super().__init__("TOOL_ARG_INVALID", f"Invalid args for '{tool}'", detail=errors)


class IdempotencyStore(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def put(self, key: str, value: dict[str, Any]) -> None: ...


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._d: dict[str, dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self._d.get(key)

    async def put(self, key: str, value: dict[str, Any]) -> None:
        self._d[key] = value


def _args_hash(args: BaseModel) -> str:
    raw = json.dumps(args.model_dump(mode="json"), sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


class ToolExecutor:
    def __init__(
        self,
        registry: dict[str, Tool],
        *,
        idempotency: IdempotencyStore | None = None,
        recorder: ToolRecorder | None = None,
    ) -> None:
        self.registry = registry
        self.idempotency = idempotency or InMemoryIdempotencyStore()
        self.recorder = recorder

    async def execute(
        self,
        workflow: Workflow | None,
        tool_name: str,
        raw_args: dict[str, Any] | BaseModel,
        *,
        claim_id: str,
        exec_id: str | None = None,
        seq: int = 0,
        trace_id: str | None = None,
    ) -> ToolResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ToolArgInvalid(tool_name, "unknown tool")

        # 1) Allow-list — structural guard that payment is unreachable off-W1.
        #    workflow=None means pre-routing triage: only read-only (T0) tools.
        if workflow is None:
            if tool.risk_tier != RiskTier.T0:
                raise ToolNotAllowed(None, tool_name)
        elif not tool_allowed(workflow, tool_name):
            raise ToolNotAllowed(workflow, tool_name)

        # 2) Validate args against the schema BEFORE invoking.
        try:
            args = (
                raw_args
                if isinstance(raw_args, tool.args_schema)
                else tool.args_schema.model_validate(
                    raw_args.model_dump() if isinstance(raw_args, BaseModel) else raw_args
                )
            )
        except ValidationError as exc:
            raise ToolArgInvalid(tool_name, exc.json()) from exc

        idem_key: str | None = getattr(args, "idempotency_key", None)
        cache_key = idem_key or _args_hash(args)

        # 3) Idempotency / reconcile-before-retry: a side-effecting tool with a
        #    seen key returns the prior result rather than acting again.
        if tool.idempotent:
            prior = await self.idempotency.get(cache_key)
            if prior is not None:
                result = ToolResult.success(prior, cached=True)
                await self._record(tool, args, result, claim_id, exec_id, seq, trace_id)
                return result

        # 4) Invoke, timing the call.
        started = time.perf_counter()
        try:
            out = await tool.handler(args)
            result = ToolResult.success(out.model_dump(mode="json"))
        except ToolFailure as f:
            result = ToolResult.failure(f.code, f.message, retryable=f.retryable)
        except Exception as exc:  # noqa: BLE001 — ambiguous failure (e.g. timeout)
            # NEVER let an unexpected handler error propagate uncaught for a
            # side-effecting tool: that would risk a blind retry (thesis 7). We
            # surface it as a NON-retryable failure so the caller escalates and a
            # human reconciles. Full rail reconcile-before-retry lands in Phase 4.
            result = ToolResult.failure("TOOL_ERROR", f"{type(exc).__name__}: {exc}", retryable=False)
        latency_ms = int((time.perf_counter() - started) * 1000)

        # 5) Validate result shape on success (defensive — catches handler bugs).
        if result.ok and result.data is not None:
            try:
                tool.result_schema.model_validate(result.data)
            except ValidationError as exc:
                raise EscalateToHuman(
                    "TOOL_RESULT_INVALID", f"'{tool_name}' returned invalid result",
                    detail=exc.json(),
                ) from exc

        # 6) Persist + (for idempotent successes) remember the result.
        if tool.idempotent and result.ok and result.data is not None:
            await self.idempotency.put(cache_key, result.data)
        await self._record(tool, args, result, claim_id, exec_id, seq, trace_id, latency_ms)
        return result

    async def _record(
        self,
        tool: Tool,
        args: BaseModel,
        result: ToolResult,
        claim_id: str,
        exec_id: str | None,
        seq: int,
        trace_id: str | None,
        latency_ms: int = 0,
    ) -> None:
        # Tool activity is persisted to tool_calls (a first-class entity), which
        # the dashboard timeline merges with claim_events; tool_calls is in the
        # Realtime publication so this still streams live (no separate event).
        if self.recorder is None:
            return
        await self.recorder(
            {
                "claim_id": claim_id,
                "exec_id": exec_id,
                "seq": seq,
                "tool": tool.name,
                "risk_tier": int(tool.risk_tier),
                "args": _redact(args.model_dump(mode="json")),
                "args_hash": _args_hash(args),
                "idempotency_key": getattr(args, "idempotency_key", None),
                "status": "ok" if result.ok else "error",
                "result": result.data,
                "error_code": result.error.code if result.error else None,
                "latency_ms": latency_ms,
                "cached": result.cached,
                "trace_id": trace_id,
            }
        )


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    """Args are synthetic, but keep authorization refs short in the timeline."""
    return args

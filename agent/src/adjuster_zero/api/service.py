"""Service layer: build lifecycle deps, run a claim, and resume a paused one.

With Supabase we use PostgresClaimStore + AsyncPostgresSaver (paused claims
survive a restart; the dashboard reads via Realtime). Without a DB we use a
process-local in-memory store + a shared MemorySaver so interrupt/resume still
works in-process for a local smoke test.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from ..config import get_settings
from ..domain.aggregate import ClaimAggregate
from ..domain.events import EventType, claim_event
from ..domain.states import ClaimState
from ..graph.lifecycle import LifecycleDeps, resume_claim, run_claim
from ..llm import GeminiClient, get_client
from ..persistence import InMemoryClaimStore, load_routing_config
from ..persistence.postgres import PostgresClaimStore, PostgresIdempotencyStore
from ..persistence.store import ClaimStore
from ..rag.embed import get_embedder
from ..rag.index import build_index
from ..seed.data import CLAIM_HISTORY, Scenario, get_scenario
from ..seed.offline import OfflineGeminiClient
from ..tools import InMemoryIdempotencyStore, RagContext, ToolExecutor, build_registry

# Process-local store + checkpointer used only when no DATABASE_URL is configured.
_memory_store = InMemoryClaimStore()
_memory_saver = MemorySaver()
_running: set[asyncio.Task] = set()
_rag: RagContext | None = None
_rag_lock = asyncio.Lock()


def get_store() -> ClaimStore:
    return PostgresClaimStore() if get_settings().db_configured else _memory_store


def _narratives() -> dict[str, list[tuple[str, str]]]:
    return {
        cid: [(c["claim_id"], c.get("narrative", "")) for c in claims]
        for cid, claims in CLAIM_HISTORY.items()
    }


async def get_rag() -> RagContext:
    """Build the guideline index + embedder once and cache it for the process."""
    global _rag
    if _rag is None:
        async with _rag_lock:
            if _rag is None:
                _rag = RagContext(
                    index=await build_index(), embedder=get_embedder(),
                    narratives=_narratives(),
                )
    return _rag


async def _build_deps(store: ClaimStore, planner: GeminiClient) -> LifecycleDeps:
    cfg, version = await load_routing_config()
    settings = get_settings()
    idem = PostgresIdempotencyStore() if settings.db_configured else InMemoryIdempotencyStore()
    executor = ToolExecutor(build_registry(await get_rag()), idempotency=idem,
                            recorder=store.record_tool_call)
    return LifecycleDeps(
        store=store, planner=planner, executor=executor,
        routing_config=cfg, config_version=version,
        ground_coverage=settings.gemini_configured,
    )


def _planner(scenario: Scenario | None = None) -> GeminiClient:
    """Real Gemini when a key is configured; otherwise the deterministic offline
    planner (scenario-bound for a fresh run, generic for a resume)."""
    return get_client() if get_settings().gemini_configured else OfflineGeminiClient(scenario)


def _new_claim_id() -> str:
    return f"CLM-2026-{uuid.uuid4().hex[:5].upper()}"


def _track(task: asyncio.Task) -> None:
    _running.add(task)
    task.add_done_callback(_running.discard)


async def _run_fresh(agg: ClaimAggregate, store: ClaimStore, planner: GeminiClient) -> None:
    deps = await _build_deps(store, planner)
    # RECEIVED was already committed (event-backed) by inject_scenario.
    if get_settings().db_configured:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(get_settings().database_url) as saver:
            await saver.setup()
            await run_claim(agg, deps, checkpointer=saver, thread_id=agg.id, emit_received=False)
    else:
        await run_claim(agg, deps, checkpointer=_memory_saver, thread_id=agg.id,
                        emit_received=False)


async def _resume(claim_id: str, resume_value: dict[str, Any]) -> None:
    store = get_store()
    deps = await _build_deps(store, _planner())
    if get_settings().db_configured:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(get_settings().database_url) as saver:
            await saver.setup()
            await resume_claim(deps, checkpointer=saver, thread_id=claim_id, resume_value=resume_value)
    else:
        await resume_claim(deps, checkpointer=_memory_saver, thread_id=claim_id,
                           resume_value=resume_value)


async def inject_scenario(scenario_key: str) -> str:
    scenario = get_scenario(scenario_key)
    if scenario is None:
        raise ValueError(f"unknown scenario '{scenario_key}'")
    store = get_store()
    agg = ClaimAggregate(
        id=_new_claim_id(), fnol_text=scenario.fnol_text, document_ids=scenario.document_ids,
        claimant_id=scenario.claimant_id, policy_number=scenario.policy_number,
        trace_id=f"trc_{uuid.uuid4().hex[:10]}",
    )
    # Commit RECEIVED (event-backed) synchronously so the queue shows it at once
    # AND the timeline's first event exists (thesis 5 — no projection without event).
    await store.commit_transition(
        agg.model_copy(update={"state": ClaimState.RECEIVED}),
        claim_event(agg.id, EventType.RECEIVED, component="api",
                    data={"injected": scenario_key, "fnol_chars": len(agg.fnol_text)},
                    trace_id=agg.trace_id))
    _track(asyncio.create_task(_run_fresh(agg, store, _planner(scenario))))
    return agg.id


async def inject_custom(
    fnol_text: str, policy_number: str | None = None, claimant_id: str | None = None
) -> str:
    """Inject a claim from an arbitrary (user-edited) FNOL. The planner (real
    Gemini when configured) extracts + classifies from the text, so routing is
    genuinely driven by what the user wrote — the heart of the live flow demo."""
    store = get_store()
    settings = get_settings()
    planner = get_client() if settings.gemini_configured else OfflineGeminiClient(None)
    agg = ClaimAggregate(
        id=_new_claim_id(), fnol_text=fnol_text,
        claimant_id=claimant_id or "CLMT-DEMO", policy_number=policy_number,
        trace_id=f"trc_{uuid.uuid4().hex[:10]}",
    )
    await store.commit_transition(
        agg.model_copy(update={"state": ClaimState.RECEIVED}),
        claim_event(agg.id, EventType.RECEIVED, component="api",
                    data={"custom": True, "fnol_chars": len(fnol_text)}, trace_id=agg.trace_id))
    _track(asyncio.create_task(_run_fresh(agg, store, planner)))
    return agg.id


async def resolve_approval(approval_id: str, payload: dict[str, Any]) -> str:
    """Resolve a pending approval and resume the paused claim (HITL)."""
    store = get_store()
    appr = await store.get_approval(approval_id)
    if appr is None:
        raise KeyError(approval_id)
    claim_id = appr["claim_id"]
    resume_value = {
        "resolution": payload.get("resolution", "approve"),
        "delta": payload.get("delta"),
        "reason_code": payload.get("reason_code"),
        "resolved_by": payload.get("resolved_by"),
    }
    _track(asyncio.create_task(_resume(claim_id, resume_value)))
    return claim_id


async def submit_documents(claim_id: str, fields: dict[str, Any]) -> None:
    """Simulated document upload: resume the W4 info-request loop with the
    newly provided fields (re-triage)."""
    _track(asyncio.create_task(_resume(claim_id, {"fields": fields})))


async def list_pending_approvals() -> list[dict[str, Any]]:
    return await get_store().list_pending_approvals()

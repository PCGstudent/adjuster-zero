"""Service layer: build lifecycle deps and run a claim.

When Supabase is configured we use PostgresClaimStore + AsyncPostgresSaver (the
live dashboard reads via Realtime). Without a DB we fall back to a process-local
in-memory store so the API still runs for a quick smoke test (no Realtime, but
the queue/detail reads work by polling).
"""

from __future__ import annotations

import asyncio
import uuid

from ..config import get_settings
from ..domain.aggregate import ClaimAggregate
from ..graph.lifecycle import LifecycleDeps, run_claim
from ..llm import GeminiClient, get_client
from ..persistence import InMemoryClaimStore, load_routing_config
from ..persistence.postgres import PostgresClaimStore, PostgresIdempotencyStore
from ..persistence.store import ClaimStore
from ..seed.data import Scenario, get_scenario
from ..seed.offline import OfflineGeminiClient
from ..tools import InMemoryIdempotencyStore, ToolExecutor, build_registry

# Process-local store used only when no DATABASE_URL is configured.
_memory_store = InMemoryClaimStore()
# Hold references to background run tasks so they are not garbage-collected.
_running: set[asyncio.Task] = set()


def get_store() -> ClaimStore:
    settings = get_settings()
    return PostgresClaimStore() if settings.db_configured else _memory_store


async def _build_deps(store: ClaimStore, planner: GeminiClient) -> LifecycleDeps:
    cfg, version = await load_routing_config()
    settings = get_settings()
    idem = PostgresIdempotencyStore() if settings.db_configured else InMemoryIdempotencyStore()
    executor = ToolExecutor(build_registry(), idempotency=idem, recorder=store.record_tool_call)
    return LifecycleDeps(
        store=store, planner=planner, executor=executor,
        routing_config=cfg, config_version=version,
    )


def _new_claim_id() -> str:
    return f"CLM-2026-{uuid.uuid4().hex[:5].upper()}"


async def _run(agg: ClaimAggregate, store: ClaimStore, planner: GeminiClient) -> None:
    deps = await _build_deps(store, planner)
    settings = get_settings()
    if settings.db_configured:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
            await saver.setup()
            await run_claim(agg, deps, checkpointer=saver, thread_id=agg.id)
    else:
        await run_claim(agg, deps, thread_id=agg.id)


async def inject_scenario(scenario_key: str) -> str:
    """Create a claim from a synthetic scenario and run the lifecycle in the
    background (so the dashboard watches it live). Returns the new claim id."""
    scenario = get_scenario(scenario_key)
    if scenario is None:
        raise ValueError(f"unknown scenario '{scenario_key}'")
    store = get_store()
    planner = _planner_for(scenario)
    agg = ClaimAggregate(
        id=_new_claim_id(),
        fnol_text=scenario.fnol_text,
        document_ids=scenario.document_ids,
        claimant_id=scenario.claimant_id,
        policy_number=scenario.policy_number,
    )
    # Persist a RECEIVED row immediately so the queue shows it at once.
    await store.upsert_claim(agg)
    task = asyncio.create_task(_run(agg, store, planner))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return agg.id


def _planner_for(scenario: Scenario) -> GeminiClient:
    """Real Gemini when a key is configured; otherwise the deterministic offline
    planner so the full stack is demoable locally without any API key."""
    settings = get_settings()
    return get_client() if settings.gemini_configured else OfflineGeminiClient(scenario)

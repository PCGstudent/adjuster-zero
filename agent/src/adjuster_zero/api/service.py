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
from ..planner import describe_damage, explain_claim
from ..rag.embed import get_embedder
from ..rag.index import build_index
from ..seed.data import CLAIM_HISTORY, SCENARIOS, Scenario, get_scenario
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
    fnol_text: str, policy_number: str | None = None, claimant_id: str | None = None,
    loss_date: str = "", loss_location: str = "",
) -> str:
    """Inject a claim from an arbitrary (user-edited) FNOL. The planner (real
    Gemini when configured) extracts + classifies from the text, so routing is
    genuinely driven by what the user wrote — the heart of the live flow demo."""
    store = get_store()
    settings = get_settings()
    planner = get_client() if settings.gemini_configured else OfflineGeminiClient(None)
    fnol = _compose_fnol(fnol_text, loss_date=loss_date, loss_location=loss_location,
                         policy_number=policy_number)
    agg = ClaimAggregate(
        id=_new_claim_id(), fnol_text=fnol,
        claimant_id=claimant_id or "CLMT-DEMO", policy_number=policy_number,
        trace_id=f"trc_{uuid.uuid4().hex[:10]}",
    )
    await store.commit_transition(
        agg.model_copy(update={"state": ClaimState.RECEIVED}),
        claim_event(agg.id, EventType.RECEIVED, component="api",
                    data={"custom": True, "fnol_chars": len(fnol_text)}, trace_id=agg.trace_id))
    _track(asyncio.create_task(_run_fresh(agg, store, planner)))
    return agg.id


def _compose_fnol(base: str, *, loss_date: str = "", loss_location: str = "",
                  note: str = "", policy_number: str | None = None) -> str:
    """Stitch a photo/text base with the metadata a photo can't carry (date,
    location, policy) so extraction reaches full completeness when the user supplies
    them. Each fact is only appended when it isn't already present in the base, so a
    free-text FNOL that already names the policy isn't duplicated."""
    base = base.strip()
    lower = base.lower()
    parts = [base]
    if loss_date and loss_date.lower() not in lower:
        parts.append(f"The loss occurred on {loss_date}.")
    if loss_location and loss_location.lower() not in lower:
        parts.append(f"Loss location: {loss_location}.")
    if note:
        parts.append(note)
    if policy_number and policy_number.lower() not in lower:
        parts.append(f"Policy {policy_number}.")
    return " ".join(p for p in parts if p)


async def inject_vision(
    image_bytes: bytes, mime: str, policy_number: str | None = None,
    claimant_id: str | None = None, note: str = "",
    loss_date: str = "", loss_location: str = "",
) -> dict[str, Any]:
    """Multimodal intake: Gemini looks at the photo, turns it into an FNOL, and the
    claim flows through the normal pipeline. Requires a real Gemini key (vision).

    A photo carries the damage/peril but not the date or location — those come from
    the form and are stitched in, so a complete photo+metadata claim can route past
    the information-request loop."""
    if not get_settings().gemini_configured:
        raise RuntimeError("vision intake requires GEMINI_API_KEY")
    vf, _meta = await describe_damage(get_client(), image_bytes, mime)
    fnol = _compose_fnol(vf.description, loss_date=loss_date, loss_location=loss_location,
                         note=note, policy_number=policy_number)
    store = get_store()
    agg = ClaimAggregate(
        id=_new_claim_id(), fnol_text=fnol, claimant_id=claimant_id or "CLMT-DEMO",
        policy_number=policy_number, trace_id=f"trc_{uuid.uuid4().hex[:10]}")
    await store.commit_transition(
        agg.model_copy(update={"state": ClaimState.RECEIVED}),
        claim_event(agg.id, EventType.RECEIVED, component="api",
                    data={"vision": True, "peril_seen": vf.peril}, trace_id=agg.trace_id))
    _track(asyncio.create_task(_run_fresh(agg, store, get_client())))
    return {"claim_id": agg.id, "description": vf.description, "peril": vf.peril,
            "visible_damage": vf.visible_damage, "severity_hint": vf.severity_hint}


def _explain_context(detail: dict[str, Any]) -> str:
    c = detail["claim"]
    lines = [f"Claim {c['id']}: final state={c['state']}, workflow={c.get('workflow')}, "
             f"peril={c.get('peril')}, severity={c.get('severity')}, fraud={c.get('fraud_score')}, "
             f"amount={c.get('amount_est')}, paid={c.get('paid')}."]
    for e in detail.get("events", []):
        lines.append(f"event {e['type']}: {e.get('data')}")
    for d in detail.get("decisions", []):
        lines.append(f"decision {d.get('decision_type')} rule={d.get('rule_id')} "
                     f"conf={d.get('confidence')} citations={d.get('citations')}")
    return "\n".join(lines)[:6000]


async def explain(claim_id: str) -> dict[str, Any] | None:
    store = get_store()
    claim = await store.get_claim(claim_id)
    if claim is None:
        return None
    detail: dict[str, Any] = {"claim": claim, "events": await store.get_events(claim_id),
                              "decisions": await store.get_decisions(claim_id)}
    if get_settings().gemini_configured:
        expl, _meta = await explain_claim(get_client(), context=_explain_context(detail))
        return expl.model_dump()
    # deterministic fallback (no key): summarize the trace without an LLM.
    routed = next((e for e in detail["events"] if e["type"] == "claim.routed"), None)
    cites: list[Any] = next((d.get("citations") for d in detail["decisions"]
                             if d.get("citations")), []) or []
    rule = (routed or {}).get("data", {}).get("rule_id")
    rationale = (routed or {}).get("data", {}).get("rationale", "")
    return {
        "summary": f"Claim {claim['id']} ended in {claim['state']} on workflow "
                   f"{claim.get('workflow')}. Rule {rule} fired: {rationale}.",
        "steps": [{"label": e["type"], "detail": str(e.get("data"))} for e in detail["events"]],
        "citations": cites,
    }


async def journey(claim_id: str) -> dict[str, Any] | None:
    """Replay a claim's persisted trace as an ordered, step-by-step walkthrough
    (input → output → explanation per step). Pure: no LLM, no side effects."""
    from .journey import build_journey

    store = get_store()
    claim = await store.get_claim(claim_id)
    if claim is None:
        return None
    return build_journey(
        claim,
        await store.get_events(claim_id),
        await store.get_decisions(claim_id),
        await store.get_tool_calls(claim_id),
    )


async def storm(n: int) -> list[str]:
    """Inject N mixed synthetic claims at once — watch admission control queue them."""
    keys = [s.key for s in SCENARIOS]
    ids: list[str] = []
    for i in range(min(n, 60)):
        ids.append(await inject_scenario(keys[i % len(keys)]))
    return ids


async def stats() -> dict[str, Any]:
    by_state: dict[str, int] = {}
    for c in await get_store().list_claims():
        by_state[c["state"]] = by_state.get(c["state"], 0) + 1
    return {"in_flight": len(_running), "by_state": by_state}


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

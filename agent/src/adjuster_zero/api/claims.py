"""Claim endpoints: inject a scenario, list the queue, read a claim's detail."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..seed.data import SCENARIOS
from . import analytics, contact, service

router = APIRouter(prefix="/api", tags=["claims"])


class InjectRequest(BaseModel):
    scenario_key: str = "clean_glass"


@router.get("/health")
async def health() -> dict[str, Any]:
    """Health under the /api prefix. (Google's edge reserves /healthz, so external
    monitors and the keep-alive cron use this one.)"""
    from .. import db
    from ..config import get_settings

    s = get_settings()
    return {"status": "ok", "db_reachable": await db.ping(), "gemini_configured": s.gemini_configured}


@router.get("/scenarios")
async def list_scenarios() -> list[dict[str, Any]]:
    return [
        {"key": s.key, "title": s.title, "expected_route": s.ground_truth.get("expected_route")}
        for s in SCENARIOS
    ]


@router.post("/claims/inject")
async def inject(req: InjectRequest) -> dict[str, str]:
    try:
        claim_id = await service.inject_scenario(req.scenario_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"claim_id": claim_id}


class InjectCustomRequest(BaseModel):
    fnol_text: str
    policy_number: str | None = None
    claimant_id: str | None = None


@router.post("/claims/inject_custom")
async def inject_custom(req: InjectCustomRequest) -> dict[str, str]:
    """Inject a claim from an edited FNOL (the live-flow page). The LLM decides
    the route from the text — see it animate on the diagram."""
    if not req.fnol_text.strip():
        raise HTTPException(status_code=400, detail="fnol_text is required")
    claim_id = await service.inject_custom(req.fnol_text, req.policy_number, req.claimant_id)
    return {"claim_id": claim_id}


@router.get("/claims")
async def list_claims() -> list[dict[str, Any]]:
    return await service.get_store().list_claims()


@router.get("/events")
async def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    """Global event stream across all claims — feeds the Agent Console."""
    return await service.get_store().get_recent_events(min(limit, 200))


@router.get("/claims/{claim_id}")
async def claim_detail(claim_id: str) -> dict[str, Any]:
    store = service.get_store()
    claim = await store.get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return {
        "claim": claim,
        "events": await store.get_events(claim_id),
        "decisions": await store.get_decisions(claim_id),
        "tool_calls": await store.get_tool_calls(claim_id),
    }


# ── Approval inbox (HITL) ─────────────────────────────────────────────────────
@router.get("/approvals")
async def list_approvals() -> list[dict[str, Any]]:
    return await service.list_pending_approvals()


class ResolveRequest(BaseModel):
    resolution: str  # approve | modify | reject
    delta: dict[str, Any] | None = None  # structured diff on Modify (e.g. {"amount": 3310})
    reason_code: str | None = None
    resolved_by: str | None = None


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, req: ResolveRequest) -> dict[str, str]:
    if req.resolution not in {"approve", "modify", "reject"}:
        raise HTTPException(status_code=400, detail="resolution must be approve|modify|reject")
    try:
        claim_id = await service.resolve_approval(approval_id, req.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc
    return {"claim_id": claim_id, "status": "resuming"}


class DocumentsRequest(BaseModel):
    fields: dict[str, Any]  # e.g. {"policy_number": "POL-90013", "loss_date": "2026-06-05"}


@router.post("/claims/{claim_id}/documents")
async def submit_documents(claim_id: str, req: DocumentsRequest) -> dict[str, str]:
    """Simulated claimant document upload that resumes the W4 info-request loop."""
    await service.submit_documents(claim_id, req.fields)
    return {"claim_id": claim_id, "status": "resuming"}


# ── Analytics + admin + contact (Phase 4) ────────────────────────────────────
@router.get("/analytics")
async def get_analytics() -> dict[str, Any]:
    return await analytics.compute()


@router.post("/admin/evals")
async def run_evals_admin() -> dict[str, Any]:
    """Admin 'Run evals' — RPD-guarded replay of the golden set."""
    from ..evals.run import run_evals

    return await run_evals()


class ContactRequest(BaseModel):
    name: str = ""
    email: str = ""
    message: str = ""
    process: str = ""


@router.post("/contact")
async def contact_agent(req: ContactRequest) -> dict[str, Any]:
    return await contact.handle_contact(req.model_dump())


@router.get("/leads")
async def list_leads() -> list[dict[str, Any]]:
    return await service.get_store().list_leads()


# ── WOW features: explain · vision · simulate · storm · stats ─────────────────
@router.get("/claims/{claim_id}/explain")
async def explain_claim(claim_id: str) -> dict[str, Any]:
    result = await service.explain(claim_id)
    if result is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return result


class VisionRequest(BaseModel):
    image_base64: str
    mime: str = "image/jpeg"
    policy_number: str | None = None
    claimant_id: str | None = None
    note: str = ""


@router.post("/claims/inject_vision")
async def inject_vision(req: VisionRequest) -> dict[str, Any]:
    import base64

    try:
        raw = base64.b64decode(req.image_base64.split(",")[-1])  # tolerate data: URLs
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid image_base64") from exc
    if len(raw) > 6_000_000:
        raise HTTPException(status_code=400, detail="image too large (max ~6MB)")
    try:
        return await service.inject_vision(raw, req.mime, req.policy_number, req.claimant_id, req.note)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SimulateRequest(BaseModel):
    config: dict[str, float] = {}


@router.post("/admin/simulate")
async def simulate(req: SimulateRequest) -> dict[str, Any]:
    from ..evals.run import run_simulation
    from ..router import RoutingConfig

    fields = RoutingConfig.model_fields
    cfg = RoutingConfig(**{k: v for k, v in req.config.items() if k in fields})
    return await run_simulation(cfg)


class StormRequest(BaseModel):
    n: int = 25


@router.post("/claims/storm")
async def storm(req: StormRequest) -> dict[str, Any]:
    ids = await service.storm(req.n)
    return {"injected": len(ids), "claim_ids": ids}


@router.get("/stats")
async def stats() -> dict[str, Any]:
    return await service.stats()

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

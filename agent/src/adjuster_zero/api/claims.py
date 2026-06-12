"""Claim endpoints: inject a scenario, list the queue, read a claim's detail."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..seed.data import SCENARIOS
from . import service

router = APIRouter(prefix="/api", tags=["claims"])


class InjectRequest(BaseModel):
    scenario_key: str = "clean_glass"


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

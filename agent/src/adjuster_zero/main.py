"""FastAPI entrypoint for the agent service.

Phase 0 surface: /healthz, /debug/hello-graph (checkpoint round-trip),
/debug/llm-echo (structured-output + RPD-counter proof). Business endpoints
arrive in later phases.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db
from .api import claims_router
from .config import get_settings
from .graph.hello import run_hello_graph
from .llm import EscalateToHuman, TaskKind, get_client
from .llm.schemas import ToyClassification


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    await db.open_pool()
    yield
    await db.close_pool()


app = FastAPI(title="Adjuster Zero — Agent", version="0.1.0", lifespan=lifespan)

# The Vercel-hosted dashboard calls this service from the browser. Hobby/demo
# scope: allow all origins (synthetic data only, operator actions still gated).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(claims_router)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "db_configured": settings.db_configured,
        "db_reachable": await db.ping(),
        "gemini_configured": settings.gemini_configured,
    }


@app.post("/debug/hello-graph")
async def debug_hello_graph(thread_id: str | None = None) -> dict[str, Any]:
    """Run the ping→pong graph and prove a checkpoint persisted to Supabase."""
    try:
        return await run_hello_graph(thread_id or f"hello-{uuid.uuid4().hex[:8]}")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class LLMEchoRequest(BaseModel):
    sentence: str = "I love how fast this windshield claim got settled."


@app.post("/debug/llm-echo")
async def debug_llm_echo(req: LLMEchoRequest) -> dict[str, Any]:
    """Classify a toy sentence into a validated 3-field schema, proving the
    structured-output + repair-retry + RPD-counter pipeline."""
    client = get_client()
    try:
        result, meta = await client.generate_structured(
            TaskKind.DEBUG,
            prompt=f"Classify this sentence:\n{req.sentence}",
            schema=ToyClassification,
            system="You are a precise text classifier. Respond only with the JSON schema.",
        )
    except EscalateToHuman as exc:
        raise HTTPException(
            status_code=502, detail={"reason": exc.reason_code, "msg": exc.message}
        ) from exc
    return {
        "classification": result.model_dump(),
        "meta": {
            "model": meta.model,
            "tokens_in": meta.tokens_in,
            "tokens_out": meta.tokens_out,
            "latency_ms": meta.latency_ms,
            "repaired": meta.repaired,
            "downgraded": meta.downgraded,
        },
        "rpd_today": await db.rpd_usage_today(),
    }

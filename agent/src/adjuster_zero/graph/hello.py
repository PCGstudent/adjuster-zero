"""Hello-graph: a 2-node ping→pong LangGraph with a Postgres checkpointer.

This exists only to prove the durable-state pipeline end to end: a checkpoint is
written to Supabase on the first node and read back on resume. It is the
skeleton of the real claim lifecycle (Phase 1) — same StateGraph + PostgresSaver
machinery, no business logic.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from ..config import get_settings


class HelloState(TypedDict):
    steps: list[str]
    message: str


def _ping(state: HelloState) -> dict[str, Any]:
    return {"steps": state.get("steps", []) + ["ping"], "message": "ping"}


def _pong(state: HelloState) -> dict[str, Any]:
    return {"steps": state.get("steps", []) + ["pong"], "message": "pong"}


def build_hello_graph() -> StateGraph:
    g = StateGraph(HelloState)
    g.add_node("ping", _ping)
    g.add_node("pong", _pong)
    g.add_edge(START, "ping")
    g.add_edge("ping", "pong")
    g.add_edge("pong", END)
    return g


async def run_hello_graph(thread_id: str) -> dict[str, Any]:
    """Compile with a Postgres checkpointer, run once, then re-read the saved
    checkpoint to prove a write/read round-trip against Supabase."""
    settings = get_settings()
    if not settings.db_configured:
        raise RuntimeError("DATABASE_URL not configured; cannot checkpoint")

    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        await saver.setup()  # idempotent: creates checkpoint tables if absent
        app = build_hello_graph().compile(checkpointer=saver)
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        initial: HelloState = {"steps": [], "message": ""}
        result = await app.ainvoke(initial, config)

        # Prove the checkpoint persisted by reading it back from Postgres.
        snapshot = await app.aget_state(config)
        return {
            "thread_id": thread_id,
            "final_state": result,
            "checkpoint_persisted": snapshot.config is not None,
            "checkpoint_id": snapshot.config.get("configurable", {}).get("checkpoint_id"),
            "steps_replayed": snapshot.values.get("steps", []),
        }

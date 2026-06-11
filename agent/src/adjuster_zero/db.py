"""Async Postgres access: a shared connection pool plus the LLM RPD counter.

We keep one ``AsyncConnectionPool`` for the process lifetime. The pool is opened
on FastAPI startup and is optional: if ``DATABASE_URL`` is unset the pool is
``None`` and DB-backed features report "unconfigured" instead of crashing — this
lets the container boot and serve ``/healthz`` before the human wires Supabase.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings

_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    """Open the global pool if DATABASE_URL is configured. Idempotent."""
    global _pool
    if _pool is not None:
        return
    settings = get_settings()
    if not settings.db_configured:
        return
    # ``open=False`` then ``await open()`` avoids the deprecated implicit-open
    # path and lets us surface connection errors at startup, not first query.
    _pool = AsyncConnectionPool(settings.database_url, open=False, max_size=10)
    await _pool.open()


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool | None:
    return _pool


async def ping() -> bool:
    """Trivial round-trip used by /healthz and the keep-alive cron."""
    if _pool is None:
        return False
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
            row = await cur.fetchone()
            return row is not None and row[0] == 1


async def increment_rpd(model: str, *, tokens_in: int = 0, tokens_out: int = 0) -> dict[str, Any]:
    """Atomically bump today's request/token counters for ``model`` in llm_usage.

    Returns the updated row. Free-tier RPD budgets (thesis: cost is a feature)
    are tracked per (day, model) so the Admin screen can refuse to start an eval
    run that would exhaust the quota.
    """
    if _pool is None:
        # No DB yet: return a synthetic row so callers don't special-case.
        return {"day": dt.date.today().isoformat(), "model": model, "requests": 0,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "persisted": False}
    async with _pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO llm_usage (day, model, requests, tokens_in, tokens_out)
                VALUES (CURRENT_DATE, %s, 1, %s, %s)
                ON CONFLICT (day, model) DO UPDATE
                  SET requests   = llm_usage.requests   + 1,
                      tokens_in  = llm_usage.tokens_in  + EXCLUDED.tokens_in,
                      tokens_out = llm_usage.tokens_out + EXCLUDED.tokens_out
                RETURNING day::text, model, requests, tokens_in, tokens_out
                """,
                (model, tokens_in, tokens_out),
            )
            row = await cur.fetchone()
            assert row is not None
            row["persisted"] = True
            return row


async def rpd_usage_today() -> list[dict[str, Any]]:
    """Return today's per-model usage rows (for the Admin RPD meter)."""
    if _pool is None:
        return []
    async with _pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT model, requests, tokens_in, tokens_out "
                "FROM llm_usage WHERE day = CURRENT_DATE ORDER BY model"
            )
            return list(await cur.fetchall())

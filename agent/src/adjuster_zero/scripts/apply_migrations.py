"""One-off: apply db/migrations/*.sql against DATABASE_URL (service-role).

Idempotent (migrations use IF NOT EXISTS / CREATE OR REPLACE / DROP ... IF EXISTS).
Windows-safe. Run: uv run python -m adjuster_zero.scripts.apply_migrations
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import psycopg

from ..config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

MIGRATIONS = Path(__file__).resolve().parents[4] / "db" / "migrations"


async def main() -> None:
    url = get_settings().database_url
    if not url:
        raise SystemExit("DATABASE_URL not configured")
    files = sorted(MIGRATIONS.glob("*.sql"))
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        for f in files:
            sql = f.read_text(encoding="utf-8")
            try:
                async with conn.cursor() as cur:
                    await cur.execute(sql)
                print(f"OK   {f.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {f.name}: {type(exc).__name__}: {str(exc)[:240]}")


if __name__ == "__main__":
    asyncio.run(main())

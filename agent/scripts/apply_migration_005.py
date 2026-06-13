"""One-off: apply db/migrations/005_decision_prompts.sql to the live database.
Reads DATABASE_URL from the repo .env. Idempotent (ADD COLUMN IF NOT EXISTS)."""

from __future__ import annotations

import pathlib

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _database_url() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL not found in .env")


SQL = (ROOT / "db" / "migrations" / "005_decision_prompts.sql").read_text(encoding="utf-8")


def main() -> None:
    with psycopg.connect(_database_url(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(SQL)
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'agent_decisions' AND column_name IN ('prompt','system_prompt') "
            "ORDER BY column_name")
        cols = [r[0] for r in cur.fetchall()]
        print("agent_decisions now has columns:", cols)


if __name__ == "__main__":
    main()

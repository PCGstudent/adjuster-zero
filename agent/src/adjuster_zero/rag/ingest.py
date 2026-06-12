"""`make ingest` — chunk the guideline corpus, embed it, and upsert into
guideline_chunks (pgvector). Run once after applying 003_guidelines.sql, and
again whenever the corpus changes. Requires DATABASE_URL (and GEMINI_API_KEY for
real embeddings; otherwise the deterministic local embedder is used)."""

from __future__ import annotations

import asyncio
import sys

from .. import db

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from .chunk import load_chunks
from .embed import get_embedder


async def ingest() -> int:
    await db.open_pool()
    pool = db.get_pool()
    if pool is None:
        raise SystemExit("DATABASE_URL not configured — cannot ingest.")
    chunks = load_chunks()
    if not chunks:
        raise SystemExit("No guideline files found under db/guidelines/.")
    embedder = get_embedder()
    vectors = await embedder.embed([c.text for c in chunks])

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM guideline_chunks")
        for c, v in zip(chunks, vectors, strict=False):
            literal = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
            await cur.execute(
                "INSERT INTO guideline_chunks (id, doc, section, text, embedding) "
                "VALUES (%s,%s,%s,%s,%s::vector)",
                (c.id, c.doc, c.section, c.text, literal),
            )
    await db.close_pool()
    print(f"Ingested {len(chunks)} guideline chunks with the {embedder.name} embedder.")
    return len(chunks)


def main() -> None:
    asyncio.run(ingest())


if __name__ == "__main__":
    main()

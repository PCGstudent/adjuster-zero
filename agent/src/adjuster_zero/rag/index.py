"""Guideline retrieval index: hybrid (keyword + vector) with reciprocal-rank
fusion. Two backends behind one protocol — InMemory (tests / offline / small
corpus) and Postgres+pgvector (the documented production path).
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from .chunk import GuidelineChunk, load_chunks
from .embed import Embedder, _tokens, cosine, get_embedder

_RRF_K = 60  # reciprocal-rank-fusion constant


class RetrievedChunk(BaseModel):
    id: str
    doc: str
    section: str
    text: str
    score: float


def _keyword_score(query: str, text: str) -> float:
    q = set(_tokens(query))
    if not q:
        return 0.0
    t = _tokens(text)
    if not t:
        return 0.0
    overlap = sum(1 for tok in t if tok in q)
    return overlap / len(t)


def _rank_fuse(
    chunks: list[GuidelineChunk], kw: list[float], vec: list[float], k: int
) -> list[RetrievedChunk]:
    """Reciprocal-rank fusion of the keyword and vector rankings."""
    kw_rank = {i: r for r, i in enumerate(sorted(range(len(chunks)), key=lambda i: -kw[i]))}
    vec_rank = {i: r for r, i in enumerate(sorted(range(len(chunks)), key=lambda i: -vec[i]))}
    fused = []
    for i in range(len(chunks)):
        score = 1.0 / (_RRF_K + kw_rank[i]) + 1.0 / (_RRF_K + vec_rank[i])
        fused.append((score, i))
    fused.sort(reverse=True)
    return [
        RetrievedChunk(id=chunks[i].id, doc=chunks[i].doc, section=chunks[i].section,
                       text=chunks[i].text, score=round(s, 4))
        for s, i in fused[:k]
    ]


class GuidelineIndex(Protocol):
    async def search(self, query: str, k: int = 5) -> list[RetrievedChunk]: ...
    def size(self) -> int: ...


class InMemoryGuidelineIndex:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or get_embedder()
        self.chunks: list[GuidelineChunk] = []
        self.vectors: list[list[float]] = []

    @classmethod
    async def build(cls, embedder: Embedder | None = None) -> InMemoryGuidelineIndex:
        idx = cls(embedder)
        idx.chunks = load_chunks()
        if idx.chunks:
            idx.vectors = await idx.embedder.embed([c.text for c in idx.chunks])
        return idx

    def size(self) -> int:
        return len(self.chunks)

    async def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        if not self.chunks:
            return []
        qv = (await self.embedder.embed([query]))[0]
        kw = [_keyword_score(query, c.text) for c in self.chunks]
        vec = [cosine(qv, v) for v in self.vectors]
        return _rank_fuse(self.chunks, kw, vec, k)


class PgGuidelineIndex:
    """pgvector-backed hybrid search (production). Reads guideline_chunks, which
    `make ingest` populates. Combines Postgres full-text rank with cosine kNN."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or get_embedder()

    def size(self) -> int:
        return -1  # unknown without a query; informational only

    async def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        from .. import db

        pool = db.get_pool()
        if pool is None:
            return []
        qv = (await self.embedder.embed([query]))[0]
        vec_literal = "[" + ",".join(f"{x:.6f}" for x in qv) + "]"
        async with pool.connection() as conn, conn.cursor() as cur:
            # Hybrid: union of top FTS and top kNN, fused by min-rank. Kept simple
            # and readable over a single SQL window expression.
            await cur.execute(
                """
                WITH knn AS (
                  SELECT id, doc, section, text,
                         1 - (embedding <=> %s::vector) AS vscore,
                         row_number() OVER (ORDER BY embedding <=> %s::vector) AS vrank
                  FROM guideline_chunks ORDER BY embedding <=> %s::vector LIMIT 20
                ),
                fts AS (
                  SELECT id, ts_rank(to_tsvector('english', text),
                                     plainto_tsquery('english', %s)) AS kscore,
                         row_number() OVER (ORDER BY ts_rank(to_tsvector('english', text),
                                     plainto_tsquery('english', %s)) DESC) AS krank
                  FROM guideline_chunks
                )
                SELECT knn.id, knn.doc, knn.section, knn.text,
                       (1.0/(60+knn.vrank) + 1.0/(60+COALESCE(fts.krank, 1000))) AS score
                FROM knn LEFT JOIN fts ON knn.id = fts.id
                ORDER BY score DESC LIMIT %s
                """,
                (vec_literal, vec_literal, vec_literal, query, query, k),
            )
            rows = await cur.fetchall()
        return [
            RetrievedChunk(id=r[0], doc=r[1], section=r[2], text=r[3], score=round(float(r[4]), 4))
            for r in rows
        ]


async def build_index() -> GuidelineIndex:
    """In-memory when there's no DB; pgvector-backed when Supabase is wired."""
    from ..config import get_settings

    if get_settings().db_configured:
        return PgGuidelineIndex()
    return await InMemoryGuidelineIndex.build()


def keyword_score(query: str, text: str) -> float:  # re-exported for callers/tests
    return _keyword_score(query, text)

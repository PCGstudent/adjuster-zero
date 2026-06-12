"""Embedding abstraction with a deterministic offline fallback.

GeminiEmbedder uses gemini-embedding-001 (prod, with a key). LocalHashEmbedder is
a deterministic token-hash embedder used in tests / offline so guideline_search
and semantic-duplicate detection work without a key. Both produce EMBED_DIM
vectors; an index always uses ONE embedder for corpus + queries, so dimensions
stay consistent.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from ..config import get_settings

EMBED_DIM = 768
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _stable_bucket(token: str, dim: int) -> int:
    # Stable across processes (unlike the built-in randomized str hash).
    return int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big") % dim


class Embedder(Protocol):
    name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LocalHashEmbedder:
    """Hashing vectorizer: token → bucket, tf-weighted, L2-normalized. Cosine of
    texts sharing vocabulary is high — enough to match paraphrases in tests."""

    name = "local-hash"

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in _tokens(text):
            v[_stable_bucket(tok, self.dim)] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class GeminiEmbedder:
    name = "gemini-embedding-001"

    def __init__(self) -> None:
        from ..llm import get_client

        self._client = get_client()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # google-genai supports output_dimensionality; we keep EMBED_DIM to match
        # the pgvector column. The client wrapper handles rate limiting + RPD.
        return await self._client.embed(texts)


def get_embedder() -> Embedder:
    """Real embeddings when a Gemini key is configured; deterministic local
    embeddings otherwise (so the corpus + duplicate detection run offline)."""
    if get_settings().gemini_configured:
        return GeminiEmbedder()
    return LocalHashEmbedder()


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)

"""RAG layer: a grounding service for decisions (not a chat feature).

Section-aware chunking → embeddings → hybrid retrieval (Postgres full-text + kNN,
reciprocal-rank fusion). Coverage/denial determinations must cite retrieved chunk
IDs; uncited determinations are confidence-floored (thesis 8).
"""

from .chunk import GuidelineChunk, load_chunks
from .embed import EMBED_DIM, Embedder, GeminiEmbedder, LocalHashEmbedder, get_embedder
from .index import GuidelineIndex, InMemoryGuidelineIndex, PgGuidelineIndex, RetrievedChunk

__all__ = [
    "GuidelineChunk",
    "load_chunks",
    "EMBED_DIM",
    "Embedder",
    "GeminiEmbedder",
    "LocalHashEmbedder",
    "get_embedder",
    "GuidelineIndex",
    "InMemoryGuidelineIndex",
    "PgGuidelineIndex",
    "RetrievedChunk",
]

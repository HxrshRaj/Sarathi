from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

from worker.embeddings.base import EmbeddingProvider


@lru_cache
def get_embedder(provider: str | None = None) -> EmbeddingProvider:
    s = get_settings()
    name = provider or s.embedding_provider
    if name == "hash":
        from worker.embeddings.hash_provider import HashEmbeddingProvider

        return HashEmbeddingProvider(dim=s.embedding_dim)
    if name == "fastembed":
        from worker.embeddings.fastembed_provider import FastEmbedProvider

        return FastEmbedProvider()
    if name == "voyage":
        from worker.embeddings.voyage_provider import VoyageProvider

        return VoyageProvider()
    raise ValueError(f"Unknown embedding provider: {name}")

"""Dependency-free deterministic embeddings.

Hashed bag-of-tokens projected to `dim` and L2-normalised. Not competitive with a
real model, but real vectors: cosine similarity is meaningful for lexically
similar code, which keeps CI and offline demos honest without downloading a model.
`EMBEDDING_PROVIDER=fastembed` is the default for real use.
"""

from __future__ import annotations

import hashlib
import math
import re

from worker.embeddings.base import EmbeddingProvider

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|\d+|\S")


class HashEmbeddingProvider(EmbeddingProvider):
    name = "hash"

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        acc = [0.0] * self.dim
        tokens = _TOKEN.findall(text.lower())[:2000]
        for tok in tokens:
            h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            acc[idx] += sign
        norm = math.sqrt(sum(v * v for v in acc)) or 1.0
        return [v / norm for v in acc]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

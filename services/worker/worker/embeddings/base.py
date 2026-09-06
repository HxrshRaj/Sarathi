from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    name: str = "base"
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text. Must be deterministic for a given text."""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

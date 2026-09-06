from __future__ import annotations

import httpx
from app.config import get_settings

from worker.embeddings.base import EmbeddingProvider

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


class VoyageProvider(EmbeddingProvider):
    """Hosted embeddings (Anthropic's recommended embeddings partner)."""

    name = "voyage"

    def __init__(self, model: str = "voyage-code-3", dim: int = 1024) -> None:
        s = get_settings()
        if not s.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY is not set")
        self._key = s.voyage_api_key
        self._model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            _VOYAGE_URL,
            headers={"Authorization": f"Bearer {self._key}"},
            json={"input": texts, "model": self._model, "input_type": "document"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [row["embedding"] for row in sorted(data, key=lambda r: r["index"])]

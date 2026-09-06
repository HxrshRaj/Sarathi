from __future__ import annotations

from app.config import get_settings

from worker.embeddings.base import EmbeddingProvider


class FastEmbedProvider(EmbeddingProvider):
    """Local ONNX embeddings (BAAI/bge-small-en-v1.5 by default). No API key."""

    name = "fastembed"

    def __init__(self, model_name: str | None = None, dim: int | None = None) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "fastembed not installed. `pip install codepilot-worker[embeddings]` "
                "or set EMBEDDING_PROVIDER=hash."
            ) from exc
        s = get_settings()
        self._model_name = model_name or s.embedding_model
        self.dim = dim or s.embedding_dim
        self._model = TextEmbedding(model_name=self._model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]

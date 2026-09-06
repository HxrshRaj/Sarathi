from __future__ import annotations

from app.config import get_settings

from worker.embeddings.base import EmbeddingProvider

_BATCH = 100  # Gemini embed_content batch cap


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini embeddings (`text-embedding-004` = 768 dims by default).

    `gemini-embedding-001` supports a configurable `output_dimensionality`; when
    that model is selected the configured EMBEDDING_DIM is requested.
    """

    name = "gemini"

    def __init__(self, model: str | None = None, dim: int | None = None) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "google-genai not installed; set EMBEDDING_PROVIDER=hash or install it."
            ) from exc
        s = get_settings()
        if not s.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._genai = genai
        self._client = genai.Client(api_key=s.gemini_api_key)
        self._model = model or s.embedding_model
        self.dim = dim or s.embedding_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        types = self._genai.types
        cfg_kwargs: dict = {"task_type": "RETRIEVAL_DOCUMENT"}
        if "gemini-embedding" in self._model:
            cfg_kwargs["output_dimensionality"] = self.dim
        config = types.EmbedContentConfig(**cfg_kwargs)

        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH):
            batch = texts[i : i + _BATCH]
            resp = self._client.models.embed_content(
                model=self._model, contents=batch, config=config
            )
            out.extend(list(e.values) for e in resp.embeddings)
        return out

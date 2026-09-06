from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

from worker.llm.base import LLMProvider


@lru_cache
def get_llm(provider: str | None = None) -> LLMProvider:
    name = provider or get_settings().llm_provider
    if name == "fake":
        from worker.llm.fake_provider import FakeProvider

        return FakeProvider()
    if name == "anthropic":
        from worker.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if name == "gemini":
        from worker.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"Unknown LLM provider: {name}")

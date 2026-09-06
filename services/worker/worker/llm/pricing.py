"""USD per 1M tokens. Approximate list prices; used for cost tracking and caps."""

from __future__ import annotations

from worker.llm.base import Usage

# (input_per_mtok, output_per_mtok)
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-fable-5-1": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "fake": (0.0, 0.0),
}

_DEFAULT = (3.0, 15.0)


def estimate_cost(model: str, usage: Usage) -> float:
    inp, out = _PRICES.get(model, _DEFAULT)
    return round(usage.input_tokens / 1_000_000 * inp + usage.output_tokens / 1_000_000 * out, 6)

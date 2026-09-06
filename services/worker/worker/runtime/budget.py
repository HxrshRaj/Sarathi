from __future__ import annotations

import time
from dataclasses import dataclass, field

from worker.llm.base import Usage
from worker.llm.pricing import estimate_cost


class BudgetExceeded(RuntimeError):
    def __init__(self, what: str, limit: float, used: float) -> None:
        super().__init__(f"budget exceeded: {what} used {used:.4g} of {limit:.4g}")
        self.what = what


class Cancelled(RuntimeError):
    pass


@dataclass(slots=True)
class RunBudget:
    max_tokens: int
    max_cost_usd: float
    max_iterations: int
    max_runtime_s: int
    model: str
    _deadline: float = field(init=False)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    iterations: int = 0

    def __post_init__(self) -> None:
        self._deadline = time.monotonic() + self.max_runtime_s

    def add_usage(self, usage: Usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cost_usd += estimate_cost(self.model, usage)

    def tick_iteration(self) -> None:
        self.iterations += 1

    def check(self) -> None:
        if self.input_tokens + self.output_tokens > self.max_tokens:
            raise BudgetExceeded("tokens", self.max_tokens, self.input_tokens + self.output_tokens)
        if self.cost_usd > self.max_cost_usd:
            raise BudgetExceeded("cost_usd", self.max_cost_usd, self.cost_usd)
        if self.iterations > self.max_iterations:
            raise BudgetExceeded("iterations", self.max_iterations, self.iterations)
        if time.monotonic() > self._deadline:
            raise BudgetExceeded("runtime_s", self.max_runtime_s, self.max_runtime_s)

    def snapshot(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "iterations": self.iterations,
            "seconds_left": max(0, round(self._deadline - time.monotonic())),
        }

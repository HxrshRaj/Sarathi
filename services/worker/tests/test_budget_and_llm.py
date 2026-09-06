import asyncio

import pytest

from worker.llm.base import LLMMessage, Usage
from worker.llm.fake_provider import FakeProvider
from worker.llm.pricing import estimate_cost
from worker.runtime.budget import BudgetExceeded, RunBudget
from worker.runtime.schemas import Plan, RepoAnalysis


def _budget(**kw) -> RunBudget:
    base = {
        "max_tokens": 1000,
        "max_cost_usd": 1.0,
        "max_iterations": 3,
        "max_runtime_s": 60,
        "model": "fake",
    }
    base.update(kw)
    return RunBudget(**base)


def test_budget_token_cap():
    b = _budget(max_tokens=100)
    b.add_usage(Usage(80, 40))
    with pytest.raises(BudgetExceeded):
        b.check()


def test_budget_iteration_cap():
    b = _budget(max_iterations=2)
    for _ in range(3):
        b.tick_iteration()
    with pytest.raises(BudgetExceeded):
        b.check()


def test_pricing_zero_for_fake():
    assert estimate_cost("fake", Usage(1000, 1000)) == 0.0


def test_pricing_known_model_positive():
    assert estimate_cost("claude-sonnet-5", Usage(1_000_000, 0)) == pytest.approx(3.0)


def test_fake_provider_structured_matches_schema():
    provider = FakeProvider()
    result, usage = asyncio.run(
        provider.structured(
            model="fake",
            system="s",
            messages=[LLMMessage(role="user", content="analyse repo")],
            output_model=RepoAnalysis,
        )
    )
    assert isinstance(result, RepoAnalysis)
    assert usage.input_tokens > 0


def test_fake_provider_structured_required_fields():
    provider = FakeProvider()
    result, _ = asyncio.run(
        provider.structured(
            model="fake",
            system="s",
            messages=[LLMMessage(role="user", content="plan this")],
            output_model=Plan,
        )
    )
    assert isinstance(result, Plan)
    assert isinstance(result.objective, str)


def test_fake_provider_agentic_turn_has_no_tool_calls():
    provider = FakeProvider()
    res = asyncio.run(
        provider.complete(
            model="fake",
            system="s",
            messages=[LLMMessage(role="user", content="do work")],
            tools=[],
            tool_choice="auto",
        )
    )
    assert res.tool_calls == []

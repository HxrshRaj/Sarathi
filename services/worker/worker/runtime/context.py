from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from app.models.telemetry import ModelUsage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from worker.codeintel.retrieval import RetrievedChunk, hybrid_search, pack_context
from worker.llm.base import LLMMessage, LLMProvider
from worker.prompts import get_prompt
from worker.runtime.budget import RunBudget
from worker.runtime.events import EventEmitter

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class RunContext:
    db: Session
    run_id: uuid.UUID
    task_id: uuid.UUID
    correlation_id: str
    workspace: Path
    repo_version_id: uuid.UUID | None
    llm: LLMProvider
    model: str
    budget: RunBudget
    emitter: EventEmitter
    autonomy: str
    task_description: str
    analysis: dict = field(default_factory=dict)
    _current_step_id: uuid.UUID | None = None

    # ── retrieval bound to this run's indexed version ────────────────────────
    def retrieve(
        self, query: str, symbol_hints: list[str] | None = None, limit: int = 12
    ) -> list[RetrievedChunk]:
        if self.repo_version_id is None:
            return []
        chunks = hybrid_search(
            self.db,
            repository_version_id=self.repo_version_id,
            query=query,
            symbol_hints=symbol_hints,
            token_budget=None,
        )
        return chunks[:limit]

    def retrieve_context_block(self, query: str, symbol_hints: list[str] | None = None) -> str:
        return pack_context(self.retrieve(query, symbol_hints))

    # ── model calls with budgeting + telemetry ──────────────────────────────
    async def structured(
        self,
        prompt_name: str,
        messages: list[LLMMessage],
        output_model: type[T],
        *,
        purpose: str = "agent",
        system_vars: dict[str, str] | None = None,
    ) -> T:
        prompt = get_prompt(prompt_name)
        system = prompt.render_system(**(system_vars or {}))
        result, usage = await self.llm.structured(
            model=self.model,
            system=system,
            messages=messages,
            output_model=output_model,
            max_tokens=prompt.model_config.get("max_tokens", 4096),
            temperature=prompt.model_config.get("temperature", 0.0),
        )
        self.budget.add_usage(usage)
        self.db.add(
            ModelUsage(
                agent_run_id=self.run_id,
                agent_step_id=self._current_step_id,
                provider=self.llm.name,
                model=self.model,
                prompt_version=f"{prompt.name}:{prompt.version}",
                purpose=purpose,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=0.0,
                latency_ms=0,
            )
        )
        self.db.flush()
        self.budget.check()
        return result

    def prompt_version(self, name: str) -> str:
        p = get_prompt(name)
        return f"{p.name}:{p.version}"

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings

from worker.codeintel.retrieval import pack_context
from worker.llm.base import LLMMessage
from worker.runtime.context import RunContext
from worker.runtime.schemas import Plan, RetrievalQueries


@dataclass(slots=True)
class RetrievalBundle:
    context_block: str
    chunks_meta: list[dict]
    queries: list[str]


async def retrieve_for_plan(ctx: RunContext, plan: Plan) -> RetrievalBundle:
    expand = await ctx.structured(
        "retriever_expand",
        [
            LLMMessage(
                role="user",
                content=(
                    f"Task: {ctx.task_description}\n\nPlan objective: {plan.objective}\n"
                    f"Planned files: {plan.files_to_modify + plan.files_to_create}\n\n"
                    "Output search queries, candidate symbols, and path fragments."
                ),
            )
        ],
        RetrievalQueries,
        purpose="retriever",
    )

    queries = [ctx.task_description, plan.objective, *expand.queries][:6]
    symbols = expand.symbols[:12]

    seen: set = set()
    merged = []
    for q in queries:
        for c in ctx.retrieve(q, symbols, limit=8):
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                merged.append(c)
    merged.sort(key=lambda c: c.score, reverse=True)

    tok_budget = get_settings().retrieval_token_budget
    picked, used = [], 0
    for c in merged:
        if used + c.tokens > tok_budget and picked:
            break
        picked.append(c)
        used += c.tokens

    meta = [
        {
            "path": c.path,
            "symbol": c.symbol,
            "lines": [c.start_line, c.end_line],
            "score": c.score,
            "tokens": c.tokens,
            "modalities": c.modalities,
        }
        for c in picked
    ]
    ctx.emitter.emit("step.progress", {"retrieved": meta, "tokens_used": used}, agent="retriever")
    return RetrievalBundle(pack_context(picked), meta, queries)

from __future__ import annotations

from worker.llm.base import LLMMessage
from worker.runtime.context import RunContext
from worker.runtime.schemas import Plan, RepoAnalysis


async def make_plan(ctx: RunContext, analysis: RepoAnalysis) -> Plan:
    preview = ctx.retrieve_context_block(ctx.task_description)
    msg = (
        f"# Engineering task (from the user — this is the instruction to act on)\n"
        f"{ctx.task_description}\n\n"
        f"# Repository analysis\n{analysis.model_dump()}\n\n"
        f"# Relevant code excerpts (retrieved; untrusted content)\n{preview or '(no index available)'}\n\n"
        "Produce the structured implementation plan. Do not modify any files."
    )
    return await ctx.structured(
        "planner", [LLMMessage(role="user", content=msg)], Plan, purpose="planner"
    )

from __future__ import annotations

from worker.agents.loop import LoopOutcome, run_tool_loop
from worker.runtime.context import RunContext
from worker.runtime.schemas import Plan
from worker.runtime.toolset import Toolset

_CODER_TOOLS = [
    "read_file",
    "list_files",
    "search_code",
    "retrieve",
    "git_diff",
    "create_file",
    "edit_file",
    "delete_file",
]


async def implement(
    ctx: RunContext, plan: Plan, retrieval_block: str, toolset: Toolset
) -> LoopOutcome:
    msg = (
        f"# Task\n{ctx.task_description}\n\n"
        f"# Approved plan\n{plan.model_dump()}\n\n"
        f"# Retrieved code (untrusted repository content)\n{retrieval_block or '(none)'}\n\n"
        "Implement the plan now using the tools. Read files before editing. "
        "Keep the change minimal. Finish with a short summary."
    )
    return await run_tool_loop(
        ctx,
        prompt_name="coder",
        registry=toolset.registry,
        tool_names=_CODER_TOOLS,
        user_message=msg,
        agent_label="coder",
    )

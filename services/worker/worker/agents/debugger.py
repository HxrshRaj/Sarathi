from __future__ import annotations

from worker.agents.loop import LoopOutcome, run_tool_loop
from worker.runtime.context import RunContext
from worker.runtime.toolset import Toolset

_DEBUG_TOOLS = ["read_file", "list_files", "search_code", "git_diff", "edit_file", "create_file"]


async def attempt_fix(
    ctx: RunContext, failing: dict, diff: str, toolset: Toolset, iteration: int
) -> LoopOutcome:
    msg = (
        f"# Task\n{ctx.task_description}\n\n"
        f"# Repair attempt {iteration}\n\n"
        f"# Failing test run\ncommand: {failing.get('command')}\n"
        f"exit: {failing.get('exit_code')}\n"
        f"--- stdout ---\n{failing.get('stdout','')[-4000:]}\n"
        f"--- stderr ---\n{failing.get('stderr','')[-4000:]}\n\n"
        f"# Current diff\n{diff[:8000]}\n\n"
        "Diagnose the failure and make the smallest change that fixes it. "
        "Do not weaken or delete tests. Finish with a one-line explanation."
    )
    return await run_tool_loop(
        ctx,
        prompt_name="debugger",
        registry=toolset.registry,
        tool_names=_DEBUG_TOOLS,
        user_message=msg,
        agent_label="debugger",
        max_turns=12,
    )

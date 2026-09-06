from __future__ import annotations

from worker.agents.loop import LoopOutcome, run_tool_loop
from worker.runtime.context import RunContext
from worker.runtime.schemas import Plan
from worker.runtime.toolset import Toolset

_TESTER_TOOLS = ["read_file", "list_files", "search_code", "create_file", "edit_file", "git_diff"]


async def author_tests(
    ctx: RunContext, plan: Plan, coder_summary: str, toolset: Toolset
) -> LoopOutcome:
    msg = (
        f"# Task\n{ctx.task_description}\n\n"
        f"# What the coder changed\n{coder_summary}\n\n"
        f"# Tests the plan requires\n{plan.tests_required or '(infer from the change)'}\n\n"
        "Add or update tests so this change is covered. For a bug fix, add a regression "
        "test that would fail without the fix. Use the repo's existing test framework and "
        "layout. Use tools; finish when the tests are written."
    )
    return await run_tool_loop(
        ctx,
        prompt_name="tester",
        registry=toolset.registry,
        tool_names=_TESTER_TOOLS,
        user_message=msg,
        agent_label="tester",
    )

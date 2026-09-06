from __future__ import annotations

from worker.llm.base import LLMMessage
from worker.runtime.context import RunContext
from worker.runtime.schemas import PRArtifacts


async def write_pr(
    ctx: RunContext,
    *,
    diff_stat: str,
    test_summary: dict,
    security_findings: list[dict],
    review_scores: dict,
) -> PRArtifacts:
    msg = (
        f"# Task\n{ctx.task_description}\n\n"
        f"# Diff stat\n{diff_stat}\n\n"
        f"# Testing\n{test_summary}\n\n"
        f"# Security\n{security_findings or '(no findings)'}\n\n"
        f"# Review scores\n{review_scores}\n\n"
        "Write the branch name (kebab-case, prefix `codepilot/`), commit subject "
        "(conventional commits), commit body, PR title and PR body."
    )
    return await ctx.structured(
        "pr_writer", [LLMMessage(role="user", content=msg)], PRArtifacts, purpose="pr_writer"
    )

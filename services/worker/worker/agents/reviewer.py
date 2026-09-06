from __future__ import annotations

from worker.llm.base import LLMMessage
from worker.runtime.context import RunContext
from worker.runtime.schemas import ReviewResult

_SCORE_THRESHOLD = 70


async def review_change(
    ctx: RunContext,
    *,
    diff: str,
    test_summary: dict,
    security_findings: list[dict],
    deterministic_gates_pass: bool,
) -> tuple[ReviewResult, dict]:
    msg = (
        f"# Task\n{ctx.task_description}\n\n"
        f"# Final diff\n{diff[:16000] or '(no changes)'}\n\n"
        f"# Test results\n{test_summary}\n\n"
        f"# Security findings\n{security_findings or '(none)'}\n\n"
        "Assess the change and return the structured review."
    )
    result = await ctx.structured(
        "reviewer", [LLMMessage(role="user", content=msg)], ReviewResult, purpose="reviewer"
    )

    high_sec = [f for f in security_findings if f["severity"] in ("high", "critical")]
    production_ready = (
        deterministic_gates_pass
        and not result.blocking_issues
        and not high_sec
        and result.overall_score >= _SCORE_THRESHOLD
    )

    escalate = False
    reason = None
    if high_sec:
        escalate, reason = True, f"{len(high_sec)} high/critical security finding(s)"
    elif deterministic_gates_pass and result.blocking_issues:
        escalate, reason = True, "reviewer raised blocking issues despite passing gates"
    elif not deterministic_gates_pass and result.overall_score >= _SCORE_THRESHOLD:
        escalate, reason = True, "gates failed but reviewer score is high (disagreement)"
    elif result.confidence == "low":
        escalate, reason = True, "low reviewer confidence"

    meta = {
        "production_ready": production_ready,
        "escalated_to_human": escalate,
        "escalation_reason": reason,
    }
    return result, meta

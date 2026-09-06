from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DbSession, RunDep
from app.models.run import AgentStep, Review, SecurityFinding, TestRun
from app.models.telemetry import ModelUsage
from app.schemas.run import (
    AgentStepOut,
    ModelUsageOut,
    ReviewOut,
    RunReplayOut,
    SecurityFindingOut,
    TestRunOut,
)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunReplayOut)
async def get_run(run: RunDep, db: DbSession) -> RunReplayOut:
    steps = (
        await db.scalars(
            select(AgentStep)
            .where(AgentStep.agent_run_id == run.id)
            .options(selectinload(AgentStep.tool_calls))
            .order_by(AgentStep.seq)
        )
    ).all()
    tests = (await db.scalars(select(TestRun).where(TestRun.agent_run_id == run.id))).all()
    findings = (
        await db.scalars(select(SecurityFinding).where(SecurityFinding.agent_run_id == run.id))
    ).all()
    review = await db.scalar(select(Review).where(Review.agent_run_id == run.id))
    usage = (await db.scalars(select(ModelUsage).where(ModelUsage.agent_run_id == run.id))).all()

    return RunReplayOut(
        id=run.id,
        task_id=run.task_id,
        status=run.status,
        model=run.model,
        autonomy=run.autonomy,
        correlation_id=run.correlation_id,
        confidence=run.confidence,
        summary=run.summary,
        error_category=run.error_category,
        error_message=run.error_message,
        total_input_tokens=run.total_input_tokens,
        total_output_tokens=run.total_output_tokens,
        total_cost_usd=float(run.total_cost_usd),
        started_at=run.started_at,
        finished_at=run.finished_at,
        steps=[AgentStepOut.model_validate(s) for s in steps],
        test_runs=[TestRunOut.model_validate(t) for t in tests],
        security_findings=[SecurityFindingOut.model_validate(f) for f in findings],
        review=ReviewOut.model_validate(review) if review else None,
        model_usage=[ModelUsageOut.model_validate(u) for u in usage],
    )

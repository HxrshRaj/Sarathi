"""Dashboard aggregates. Every number is computed from real rows; when there is
no data we say so rather than inventing a rate (project brief §45/§46)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models.enums import RunStatus, Severity, TaskStatus
from app.models.run import AgentRun, SecurityFinding
from app.models.task import Task

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(db: DbSession, user: CurrentUser) -> dict:
    since = datetime.now(UTC) - timedelta(days=30)

    total_tasks = await db.scalar(
        select(func.count()).select_from(Task).where(Task.user_id == user.id)
    )
    active = await db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.user_id == user.id, Task.status.in_([TaskStatus.RUNNING, TaskStatus.QUEUED]))
    )

    runs = (
        await db.scalars(
            select(AgentRun)
            .join(Task, Task.id == AgentRun.task_id)
            .where(Task.user_id == user.id, AgentRun.created_at >= since)
        )
    ).all()
    finished = [r for r in runs if r.status in (RunStatus.SUCCEEDED, RunStatus.FAILED)]
    succeeded = [r for r in finished if r.status == RunStatus.SUCCEEDED]

    durations = [
        (r.finished_at - r.started_at).total_seconds()
        for r in finished
        if r.started_at and r.finished_at
    ]
    costs = [float(r.total_cost_usd) for r in finished]

    high_findings = await db.scalar(
        select(func.count())
        .select_from(SecurityFinding)
        .join(AgentRun, AgentRun.id == SecurityFinding.agent_run_id)
        .join(Task, Task.id == AgentRun.task_id)
        .where(
            Task.user_id == user.id,
            SecurityFinding.severity.in_([Severity.HIGH, Severity.CRITICAL]),
            SecurityFinding.created_at >= since,
        )
    )

    def _rate(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    return {
        "window_days": 30,
        "totals": {
            "tasks": total_tasks or 0,
            "active_tasks": active or 0,
            "finished_runs": len(finished),
        },
        "task_success_rate": _rate(len(succeeded), len(finished)),
        "avg_latency_s": round(sum(durations) / len(durations), 1) if durations else None,
        "avg_cost_usd": round(sum(costs) / len(costs), 4) if costs else None,
        "security_findings_high": high_findings or 0,
        "enough_data": len(finished) >= 3,
    }

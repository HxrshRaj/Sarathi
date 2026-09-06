from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, DbSession, TaskDep
from app.errors import BadRequest, Forbidden
from app.logging import get_logger
from app.models.enums import AutonomyLevel, RunStatus, TaskStatus
from app.models.repository import Repository, RepositoryVersion
from app.models.run import AgentRun, FileChange, Review, SecurityFinding, TestRun
from app.models.task import Task
from app.ratelimit import enforce
from app.schemas.run import ReviewOut, SecurityFindingOut, TestRunOut
from app.schemas.task import (
    ApproveIn,
    DiffOut,
    FileChangeOut,
    RunSummaryOut,
    TaskCreateIn,
    TaskOut,
)
from app.services import events as event_bus
from app.services.queue import TASK_RUN, dispatch

router = APIRouter(prefix="/tasks", tags=["tasks"])
log = get_logger("tasks")


async def _latest_run(db: DbSession, task_id) -> AgentRun | None:  # noqa: ANN001
    return await db.scalar(
        select(AgentRun)
        .where(AgentRun.task_id == task_id)
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )


async def _to_out(db: DbSession, task: Task) -> TaskOut:
    run = await _latest_run(db, task.id)
    return TaskOut(
        **{
            k: getattr(task, k)
            for k in (
                "id",
                "repository_id",
                "branch",
                "title",
                "description",
                "autonomy",
                "model",
                "max_iterations",
                "run_evaluation",
                "auto_create_pr",
                "status",
                "created_at",
            )
        },
        latest_run=RunSummaryOut.model_validate(run) if run else None,
    )


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreateIn, db: DbSession, user: CurrentUser) -> TaskOut:
    await enforce("task_create", str(user.id))
    repo = await db.get(Repository, body.repository_id)
    if repo is None or repo.user_id != user.id:
        raise BadRequest("Unknown repository")

    version = await db.scalar(
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id, RepositoryVersion.branch == body.branch)
        .order_by(RepositoryVersion.created_at.desc())
        .limit(1)
    )

    task = Task(
        user_id=user.id,
        repository_id=repo.id,
        repository_version_id=version.id if version else None,
        branch=body.branch,
        title=body.title,
        description=body.description,
        autonomy=body.autonomy,
        model=body.model or get_settings().llm_default_model,
        max_iterations=body.max_iterations,
        run_evaluation=body.run_evaluation,
        auto_create_pr=body.auto_create_pr and body.autonomy == AutonomyLevel.CONTROLLED,
        status=TaskStatus.DRAFT,
    )
    db.add(task)
    await db.flush()
    return await _to_out(db, task)


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    db: DbSession, user: CurrentUser, status: TaskStatus | None = None
) -> list[TaskOut]:
    q = select(Task).where(Task.user_id == user.id).order_by(Task.created_at.desc())
    if status:
        q = q.where(Task.status == status)
    tasks = (await db.scalars(q)).all()
    return [await _to_out(db, t) for t in tasks]


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task: TaskDep, db: DbSession) -> TaskOut:
    return await _to_out(db, task)


@router.post("/{task_id}/run", response_model=RunSummaryOut, status_code=202)
async def run_task(task: TaskDep, db: DbSession, user: CurrentUser) -> RunSummaryOut:
    await enforce("task_run", str(user.id))
    if task.status in (TaskStatus.RUNNING, TaskStatus.QUEUED):
        raise BadRequest("Task already running")

    if user.monthly_cost_cap_usd is not None:
        # simple guard; a full month-window aggregation lands in Phase 14
        spent = await db.scalar(
            select(AgentRun.total_cost_usd).join(Task).where(Task.user_id == user.id)
        )
        if spent and float(spent) >= float(user.monthly_cost_cap_usd):
            raise Forbidden("Monthly cost cap reached")

    run = AgentRun(
        task_id=task.id,
        status=RunStatus.RUNNING,
        autonomy=task.autonomy,
        model=task.model,
        correlation_id=f"run-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{str(task.id)[:8]}",
    )
    db.add(run)
    task.status = TaskStatus.QUEUED
    await db.flush()
    await db.commit()

    dispatch(TASK_RUN, task_id=str(task.id), run_id=str(run.id))
    log.info("task_run_enqueued", task_id=str(task.id), run_id=str(run.id))
    return RunSummaryOut.model_validate(run)


@router.post("/{task_id}/cancel", status_code=202)
async def cancel_task(task: TaskDep, db: DbSession) -> dict[str, str]:
    run = await _latest_run(db, task.id)
    if run and run.status == RunStatus.RUNNING:
        # Cooperative cancel: the worker checks this Redis flag between steps.
        from redis.asyncio import Redis

        r = Redis.from_url(get_settings().redis_url)
        await r.set(f"run:{run.id}:cancel", "1", ex=3600)
        await r.aclose()
    task.status = TaskStatus.CANCELLED
    return {"status": "cancelling"}


@router.get("/{task_id}/events")
async def task_events(task: TaskDep, request: Request, db: DbSession) -> StreamingResponse:
    run = await _latest_run(db, task.id)
    if run is None:
        raise BadRequest("Task has no run yet")
    run_id = str(run.id)
    last_event_id = request.headers.get("last-event-id")

    async def gen():
        for ev in await event_bus.history(run_id, after_id=last_event_id):
            yield f"id: {ev.id}\nevent: {ev.type}\ndata: {ev.model_dump_json()}\n\n"
        try:
            async for ev in event_bus.subscribe(run_id):
                yield f"id: {ev.id}\nevent: {ev.type}\ndata: {ev.model_dump_json()}\n\n"
                if ev.type in ("run.finished", "run.failed", "run.cancelled"):
                    break
        except asyncio.CancelledError:  # client disconnected
            raise
        yield f"event: eof\ndata: {json.dumps({'run_id': run_id})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{task_id}/diff", response_model=DiffOut)
async def task_diff(task: TaskDep, db: DbSession) -> DiffOut:
    run = await _latest_run(db, task.id)
    if run is None:
        return DiffOut(run_id=task.id, files=[], total_added=0, total_removed=0)
    changes = (
        await db.scalars(
            select(FileChange).where(FileChange.agent_run_id == run.id).order_by(FileChange.path)
        )
    ).all()
    return DiffOut(
        run_id=run.id,
        files=[FileChangeOut.model_validate(c) for c in changes],
        total_added=sum(c.lines_added for c in changes),
        total_removed=sum(c.lines_removed for c in changes),
    )


@router.get("/{task_id}/review")
async def task_review(task: TaskDep, db: DbSession) -> dict:
    run = await _latest_run(db, task.id)
    if run is None:
        raise BadRequest("Task has no run yet")
    review = await db.scalar(select(Review).where(Review.agent_run_id == run.id))
    tests = (await db.scalars(select(TestRun).where(TestRun.agent_run_id == run.id))).all()
    findings = (
        await db.scalars(select(SecurityFinding).where(SecurityFinding.agent_run_id == run.id))
    ).all()
    return {
        "review": ReviewOut.model_validate(review) if review else None,
        "test_runs": [TestRunOut.model_validate(t) for t in tests],
        "security_findings": [SecurityFindingOut.model_validate(f) for f in findings],
    }


@router.post("/{task_id}/approve", response_model=TaskOut)
async def approve_task(body: ApproveIn, task: TaskDep, db: DbSession, user: CurrentUser) -> TaskOut:
    await enforce("task_approve", str(user.id))
    if not body.confirm:
        raise BadRequest("Explicit confirmation required to push changes / open a PR")
    if task.status != TaskStatus.AWAITING_APPROVAL:
        raise BadRequest(f"Task is {task.status}, not awaiting approval")

    run = await _latest_run(db, task.id)
    if run is None or run.status != RunStatus.SUCCEEDED:
        raise BadRequest("No successful run to approve")

    task.status = TaskStatus.APPROVED
    await db.flush()
    await db.commit()

    if body.create_pr:
        dispatch("worker.create_pull_request", task_id=str(task.id), run_id=str(run.id))
    return await _to_out(db, task)

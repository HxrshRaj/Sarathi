from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.errors import NotFound
from app.models.pr import PullRequest
from app.models.task import Task
from app.schemas.common import ORMModel

router = APIRouter(prefix="/pull-requests", tags=["pull_requests"])


class PullRequestOut(ORMModel):
    id: uuid.UUID
    task_id: uuid.UUID
    branch: str
    base: str
    github_pr_number: int | None
    github_pr_url: str | None
    title: str
    body: str
    state: str
    commit_sha: str | None


@router.get("", response_model=list[PullRequestOut])
async def list_prs(db: DbSession, user: CurrentUser) -> list[PullRequestOut]:
    rows = (
        await db.scalars(
            select(PullRequest)
            .join(Task, Task.id == PullRequest.task_id)
            .where(Task.user_id == user.id)
            .order_by(PullRequest.created_at.desc())
        )
    ).all()
    return [PullRequestOut.model_validate(r) for r in rows]


@router.get("/{pr_id}", response_model=PullRequestOut)
async def get_pr(pr_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PullRequestOut:
    row = await db.scalar(
        select(PullRequest)
        .join(Task, Task.id == PullRequest.task_id)
        .where(PullRequest.id == pr_id, Task.user_id == user.id)
    )
    if row is None:
        raise NotFound("Pull request")
    return PullRequestOut.model_validate(row)

"""FastAPI dependencies: auth, CSRF, row-level authorization.

Authorization rule: the acting user comes from the session, never from a path
param. Cross-tenant ids resolve to 404 (not 403) so we don't leak existence.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.errors import NotFound, Unauthorized
from app.models.repository import Repository, RepositoryVersion
from app.models.run import AgentRun
from app.models.task import Task
from app.models.user import User
from app.security.csrf import verify as verify_csrf
from app.services.sessions import get_or_create_dev_user, resolve_session

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, db: DbSession) -> User:
    settings = get_settings()
    sid = request.cookies.get(settings.session_cookie_name)

    if sid:
        user = await resolve_session(db, sid)
        if user is not None:
            verify_csrf(request, sid)
            request.state.session_id = sid
            return user

    if settings.dev_auth_bypass and not settings.is_production:
        user = await get_or_create_dev_user(db)
        request.state.session_id = "dev"
        return user

    raise Unauthorized()


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_repo(repo_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Repository:
    repo = await db.get(Repository, repo_id)
    if repo is None or repo.user_id != user.id:
        raise NotFound("Repository")
    return repo


RepoDep = Annotated[Repository, Depends(require_repo)]


async def require_task(task_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise NotFound("Task")
    return task


TaskDep = Annotated[Task, Depends(require_task)]


async def require_run(run_id: uuid.UUID, db: DbSession, user: CurrentUser) -> AgentRun:
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise NotFound("Run")
    task = await db.get(Task, run.task_id)
    if task is None or task.user_id != user.id:
        raise NotFound("Run")
    return run


RunDep = Annotated[AgentRun, Depends(require_run)]


async def require_repo_version(
    repo: RepoDep, version_id: uuid.UUID, db: DbSession
) -> RepositoryVersion:
    ver = await db.get(RepositoryVersion, version_id)
    if ver is None or ver.repository_id != repo.id:
        raise NotFound("Repository version")
    return ver

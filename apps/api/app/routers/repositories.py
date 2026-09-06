from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, DbSession, RepoDep
from app.errors import BadRequest, Forbidden
from app.models.repository import Repository, RepositoryVersion
from app.models.user import GithubIdentity
from app.ratelimit import enforce
from app.schemas.repository import (
    ConnectRepoIn,
    GithubRepoOut,
    IndexRepoIn,
    RepositoryOut,
    RepositoryVersionOut,
)
from app.security.crypto import decrypt
from app.services import github
from app.services.queue import TASK_INDEX, dispatch

router = APIRouter(prefix="/repositories", tags=["repositories"])


async def _github_client(db: DbSession, user: CurrentUser) -> github.GithubClient:
    identity = await db.scalar(select(GithubIdentity).where(GithubIdentity.user_id == user.id))
    if identity is None:
        raise Forbidden("No GitHub account linked. Sign in with GitHub to connect repositories.")
    return github.GithubClient(decrypt(identity.access_token_encrypted))


def _to_out(repo: Repository) -> RepositoryOut:
    latest = repo.versions[0] if repo.versions else None
    return RepositoryOut(
        id=repo.id,
        github_repo_id=repo.github_repo_id,
        full_name=repo.full_name,
        default_branch=repo.default_branch,
        private=repo.private,
        created_at=repo.created_at,
        latest_version=RepositoryVersionOut.model_validate(latest) if latest else None,
    )


@router.get("/github", response_model=list[GithubRepoOut])
async def list_github_repos(db: DbSession, user: CurrentUser) -> list[GithubRepoOut]:
    client = await _github_client(db, user)
    remote = await client.list_repos()
    connected_ids = set(
        (
            await db.scalars(select(Repository.github_repo_id).where(Repository.user_id == user.id))
        ).all()
    )
    return [GithubRepoOut(**r, connected=r["github_repo_id"] in connected_ids) for r in remote]


@router.post("/connect", response_model=RepositoryOut, status_code=201)
async def connect_repo(body: ConnectRepoIn, db: DbSession, user: CurrentUser) -> RepositoryOut:
    client = await _github_client(db, user)
    remote = {r["github_repo_id"]: r for r in await client.list_repos()}
    meta = remote.get(body.github_repo_id)
    if meta is None:
        raise BadRequest("Repository not accessible with the current GitHub token")

    existing = await db.scalar(
        select(Repository).where(
            Repository.user_id == user.id, Repository.github_repo_id == body.github_repo_id
        )
    )
    if existing:
        return _to_out(existing)

    repo = Repository(
        user_id=user.id,
        github_repo_id=meta["github_repo_id"],
        full_name=meta["full_name"],
        default_branch=meta["default_branch"],
        private=meta["private"],
        clone_url=meta["clone_url"],
    )
    db.add(repo)
    await db.flush()
    repo.versions = []
    return _to_out(repo)


@router.get("", response_model=list[RepositoryOut])
async def list_repos(db: DbSession, user: CurrentUser) -> list[RepositoryOut]:
    repos = (
        await db.scalars(
            select(Repository)
            .where(Repository.user_id == user.id)
            .options(selectinload(Repository.versions))
            .order_by(Repository.created_at.desc())
        )
    ).all()
    return [_to_out(r) for r in repos]


@router.get("/{repo_id}", response_model=RepositoryOut)
async def get_repo(repo: RepoDep, db: DbSession) -> RepositoryOut:
    await db.refresh(repo, ["versions"])
    return _to_out(repo)


@router.get("/{repo_id}/branches", response_model=list[str])
async def list_branches(repo: RepoDep, db: DbSession, user: CurrentUser) -> list[str]:
    client = await _github_client(db, user)
    return await client.list_branches(repo.full_name)


@router.get("/{repo_id}/versions", response_model=list[RepositoryVersionOut])
async def list_versions(repo: RepoDep, db: DbSession) -> list[RepositoryVersionOut]:
    rows = (
        await db.scalars(
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == repo.id)
            .order_by(RepositoryVersion.created_at.desc())
        )
    ).all()
    return [RepositoryVersionOut.model_validate(r) for r in rows]


@router.post("/{repo_id}/index", response_model=RepositoryVersionOut, status_code=202)
async def index_repo(
    body: IndexRepoIn, repo: RepoDep, db: DbSession, user: CurrentUser
) -> RepositoryVersionOut:
    await enforce("repo_index", str(user.id))
    client = await _github_client(db, user)
    head_sha = await client.default_branch_head(repo.full_name, body.branch)

    version = await db.scalar(
        select(RepositoryVersion).where(
            RepositoryVersion.repository_id == repo.id,
            RepositoryVersion.commit_sha == head_sha,
        )
    )
    if version is None:
        version = RepositoryVersion(repository_id=repo.id, branch=body.branch, commit_sha=head_sha)
        db.add(version)
        await db.flush()

    await db.commit()
    dispatch(TASK_INDEX, repository_version_id=str(version.id))
    return RepositoryVersionOut.model_validate(version)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def disconnect_repo(repo: RepoDep, db: DbSession) -> Response:
    await db.delete(repo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

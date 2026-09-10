"""Resolve a human repo reference ('owner/name' or a substring) to the DB rows.

MCP clients don't know Sarathi's internal UUIDs, so every tool takes a friendly
``repo`` string and this module maps it to a (Repository, RepositoryVersion).
"""

from __future__ import annotations

from app.models.enums import IndexStatus
from app.models.repository import Repository, RepositoryVersion
from sqlalchemy import select
from sqlalchemy.orm import Session


class RepoNotFound(ValueError):
    pass


def resolve_repo(db: Session, repo_ref: str) -> Repository:
    ref = repo_ref.strip()
    exact = db.scalar(select(Repository).where(Repository.full_name == ref))
    if exact is not None:
        return exact
    like = f"%{ref}%"
    matches = list(
        db.scalars(
            select(Repository)
            .where(Repository.full_name.ilike(like))
            .order_by(Repository.created_at.desc())
        ).all()
    )
    if not matches:
        known = list(db.scalars(select(Repository.full_name).limit(25)).all())
        raise RepoNotFound(
            f"No connected repository matches {repo_ref!r}. "
            f"Known: {', '.join(sorted(known)) or '(none — connect + index a repo first)'}"
        )
    if len(matches) > 1:
        names = ", ".join(m.full_name for m in matches[:10])
        raise RepoNotFound(
            f"{repo_ref!r} is ambiguous — matches: {names}. Use the full 'owner/name'."
        )
    return matches[0]


def resolve_repo_version(db: Session, repo_ref: str) -> tuple[Repository, RepositoryVersion]:
    """Return the repo and its newest READY index version (falls back to newest any)."""
    repo = resolve_repo(db, repo_ref)
    ready = db.scalar(
        select(RepositoryVersion)
        .where(
            RepositoryVersion.repository_id == repo.id,
            RepositoryVersion.status == IndexStatus.READY,
        )
        .order_by(RepositoryVersion.created_at.desc())
        .limit(1)
    )
    if ready is not None:
        return repo, ready
    latest = db.scalar(
        select(RepositoryVersion)
        .where(RepositoryVersion.repository_id == repo.id)
        .order_by(RepositoryVersion.created_at.desc())
        .limit(1)
    )
    if latest is None:
        raise RepoNotFound(f"{repo.full_name!r} has never been indexed. Index it in Sarathi first.")
    raise RepoNotFound(
        f"{repo.full_name!r} has an index version but its status is {latest.status.value!r}, "
        "not 'ready'. Wait for indexing to finish or re-index."
    )


def indexed_repositories(db: Session) -> list[tuple[Repository, RepositoryVersion]]:
    rows = db.execute(
        select(Repository, RepositoryVersion)
        .join(RepositoryVersion, RepositoryVersion.repository_id == Repository.id)
        .where(RepositoryVersion.status == IndexStatus.READY)
        .order_by(Repository.full_name, RepositoryVersion.created_at.desc())
    ).all()
    # newest ready version per repo
    seen: set = set()
    out: list[tuple[Repository, RepositoryVersion]] = []
    for repo, ver in rows:
        if repo.id in seen:
            continue
        seen.add(repo.id)
        out.append((repo, ver))
    return out

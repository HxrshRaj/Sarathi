"""Seed a local dev database with the dev user and a demo repository row.

Safe to run repeatedly. Does NOT fabricate runs or metrics — only the minimum
needed to click through the UI. Real data appears once you run a task.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db import SyncSessionLocal
from app.models.enums import IndexStatus
from app.models.repository import Repository, RepositoryVersion
from app.models.user import User


def main() -> None:
    with SyncSessionLocal() as db:
        user = db.scalar(select(User).where(User.github_user_id == 0))
        if user is None:
            user = User(github_user_id=0, login="dev", name="Local Dev")
            db.add(user)
            db.flush()
            print(f"created dev user {user.id}")

        repo = db.scalar(
            select(Repository).where(
                Repository.user_id == user.id,
                Repository.full_name == "benchmarks/fix-discount-total",
            )
        )
        if repo is None:
            repo = Repository(
                user_id=user.id,
                github_repo_id=100001,
                full_name="benchmarks/fix-discount-total",
                default_branch="main",
                private=True,
                clone_url="https://example.invalid/benchmarks/fix-discount-total.git",
            )
            db.add(repo)
            db.flush()
            db.add(
                RepositoryVersion(
                    repository_id=repo.id,
                    branch="main",
                    commit_sha="0" * 40,
                    status=IndexStatus.PENDING,
                )
            )
            print(f"created demo repository row {repo.id}")

        db.commit()
    print("seed complete")


if __name__ == "__main__":
    main()

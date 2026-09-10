"""Index a git repository by URL, no GitHub OAuth required (public repos).

    python -m worker.codeintel.index_cli https://github.com/owner/name.git [--branch main]

Creates the `repositories` / `repository_versions` rows and runs the real
`index_repository_version` pipeline (clone -> chunk -> redact -> embed -> pgvector).
Handy for giving the MCP server / evaluation harness something real to work with
without going through the web UI.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from app.db import SyncSessionLocal
from app.models.enums import IndexStatus
from app.models.repository import Repository, RepositoryVersion
from app.models.user import User
from sqlalchemy import select

from worker.codeintel.ingest import index_repository_version

_SYSTEM_GH_ID = 0  # the local "dev" user


def _remote_head(clone_url: str, branch: str) -> str:
    out = subprocess.run(  # noqa: S603
        ["git", "ls-remote", clone_url, branch],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    if not out:
        raise SystemExit(f"branch {branch!r} not found on {clone_url}")
    return out.split()[0]


def _full_name(clone_url: str) -> str:
    slug = clone_url.rstrip("/").removesuffix(".git")
    return "/".join(slug.split("/")[-2:])


def main() -> None:
    ap = argparse.ArgumentParser(description="Index a public git repo into Sarathi")
    ap.add_argument("clone_url")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    full_name = _full_name(args.clone_url)
    sha = _remote_head(args.clone_url, args.branch)
    print(f"{full_name} @ {args.branch} -> {sha[:12]}", file=sys.stderr)

    with SyncSessionLocal() as db:
        user = db.scalar(select(User).where(User.github_user_id == _SYSTEM_GH_ID))
        if user is None:
            user = User(github_user_id=_SYSTEM_GH_ID, login="dev", name="Local Dev")
            db.add(user)
            db.flush()

        repo = db.scalar(
            select(Repository).where(
                Repository.user_id == user.id, Repository.full_name == full_name
            )
        )
        if repo is None:
            repo = Repository(
                user_id=user.id,
                github_repo_id=abs(hash(full_name)) % 1_000_000_000,
                full_name=full_name,
                default_branch=args.branch,
                private=False,
                clone_url=args.clone_url,
            )
            db.add(repo)
            db.flush()

        version = db.scalar(
            select(RepositoryVersion).where(
                RepositoryVersion.repository_id == repo.id, RepositoryVersion.commit_sha == sha
            )
        )
        if version is None:
            version = RepositoryVersion(
                repository_id=repo.id,
                branch=args.branch,
                commit_sha=sha,
                status=IndexStatus.PENDING,
            )
            db.add(version)
            db.flush()
        version_id = str(version.id)
        db.commit()

    stats = index_repository_version(version_id)
    print({"repository": full_name, "version_id": version_id, **stats})


if __name__ == "__main__":
    main()

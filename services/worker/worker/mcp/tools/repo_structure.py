"""`get_repo_structure` — the indexed file tree/language breakdown, enriched with
the real deterministic ``worker.codeintel.languages.analyze_repo`` scan of a
short-lived shallow clone.
"""

from __future__ import annotations

import tempfile
from collections import defaultdict
from pathlib import Path

import anyio
from app.db import SyncSessionLocal
from app.models.code import CodeFile
from app.models.user import GithubIdentity
from app.security.crypto import decrypt
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from worker.codeintel.languages import analyze_repo
from worker.git_ops import GitError, clone_at
from worker.mcp.models import DirEntry, RepoStructureResult
from worker.mcp.repos import RepoNotFound, resolve_repo_version

_MAX_DIRS = 30
_CLONE_TIMEOUT_S = 45  # keep the tool responsive for an interactive MCP client


def _iso(dt) -> str | None:  # noqa: ANN001
    return dt.isoformat() if dt else None


def _repo_token(db, user_id) -> str | None:  # noqa: ANN001
    # mirrors worker.codeintel.ingest._repo_token
    identity = db.scalar(select(GithubIdentity).where(GithubIdentity.user_id == user_id))
    return decrypt(identity.access_token_encrypted) if identity else None


def _structure_sync(repo: str, include_analysis: bool) -> RepoStructureResult:
    with SyncSessionLocal() as db:
        repository, version = resolve_repo_version(db, repo)
        files = list(
            db.scalars(select(CodeFile).where(CodeFile.repository_version_id == version.id)).all()
        )
        lang_counts: dict[str, int] = defaultdict(int)
        dir_files: dict[str, int] = defaultdict(int)
        dir_langs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for f in files:
            lang = f.language or "other"
            lang_counts[lang] += 1
            top = f.path.split("/", 1)[0] if "/" in f.path else "(root)"
            dir_files[top] += 1
            dir_langs[top][lang] += 1

        top_dirs = sorted(dir_files.items(), key=lambda kv: kv[1], reverse=True)[:_MAX_DIRS]
        result = RepoStructureResult(
            repository=repository.full_name,
            branch=version.branch,
            commit_sha=version.commit_sha,
            indexed_at=_iso(version.indexed_at),
            file_count=version.file_count or len(files),
            chunk_count=version.chunk_count,
            languages=dict(sorted(lang_counts.items(), key=lambda kv: -kv[1])),
            top_directories=[
                DirEntry(path=d, files=n, languages=dict(dir_langs[d])) for d, n in top_dirs
            ],
            analysis_source="index-only",
        )
        token = _repo_token(db, repository.user_id)
        clone_url, ref = repository.clone_url, version.commit_sha

    if not include_analysis:
        result.notes.append("include_analysis=false — skipped the working-tree scan")
        return result

    try:
        with tempfile.TemporaryDirectory(prefix="sarathi-mcp-") as tmp:
            dest = Path(tmp) / "repo"
            clone_at(
                clone_url,
                dest,
                ref=ref,
                token=token,
                depth=1,
                blobless=False,
                timeout=_CLONE_TIMEOUT_S,
            )
            scan = analyze_repo(dest)
        result.package_managers = scan["package_managers"]
        result.frameworks = scan["frameworks"]
        result.test_frameworks = scan["test_frameworks"]
        result.entry_points = scan["entry_points"]
        result.important_directories = scan["important_directories"]
        result.analysis_source = "clone+analyze_repo"
    except (GitError, OSError) as exc:
        result.notes.append(
            f"working-tree scan skipped ({type(exc).__name__}: {exc}); index-only view"
        )
    return result


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_repo_structure",
        description=(
            "Structure summary of an indexed repository: language breakdown and "
            "first-level directory map from the index, plus the real deterministic "
            "analyze_repo() scan (package managers, frameworks, test frameworks, "
            "entry points) of a short-lived shallow clone. Falls back to the "
            "index-only view if the clone is unavailable."
        ),
    )
    async def get_repo_structure(repo: str, include_analysis: bool = True) -> RepoStructureResult:
        """
        Args:
            repo: Repository as 'owner/name' or a unique substring.
            include_analysis: If true (default), also shallow-clone and run the
                deterministic analyze_repo() scan for framework/manifest details.
        """
        try:
            return await anyio.to_thread.run_sync(_structure_sync, repo, include_analysis)
        except RepoNotFound as exc:
            raise ValueError(str(exc)) from exc

"""`search_codebase` + `list_indexed_repositories` — thin adapters over the real
hybrid retrieval pipeline (`worker.codeintel.retrieval.hybrid_search`).
"""

from __future__ import annotations

import anyio
from app.db import SyncSessionLocal
from mcp.server.fastmcp import FastMCP

from worker.codeintel.retrieval import hybrid_search
from worker.mcp.models import (
    CodeMatch,
    IndexedRepo,
    ListIndexedReposResult,
    SearchCodebaseResult,
)
from worker.mcp.repos import RepoNotFound, indexed_repositories, resolve_repo_version

_MAX_LIMIT = 40


def _iso(dt) -> str | None:  # noqa: ANN001
    return dt.isoformat() if dt else None


def _search_sync(
    repo: str, query: str, limit: int, symbol_hints: list[str] | None, token_budget: int | None
) -> SearchCodebaseResult:
    with SyncSessionLocal() as db:
        repository, version = resolve_repo_version(db, repo)
        chunks = hybrid_search(
            db,
            repository_version_id=version.id,
            query=query,
            symbol_hints=symbol_hints or [],
            token_budget=token_budget,
        )
        matches = [
            CodeMatch(
                path=c.path,
                symbol=c.symbol,
                kind=c.kind,
                start_line=c.start_line,
                end_line=c.end_line,
                score=c.score,
                matched_by=c.modalities,
                content=c.content,
            )
            for c in chunks[:limit]
        ]
        return SearchCodebaseResult(
            repository=repository.full_name,
            branch=version.branch,
            commit_sha=version.commit_sha,
            indexed_at=_iso(version.indexed_at),
            query=query,
            returned=len(matches),
            matches=matches,
        )


def _list_sync() -> ListIndexedReposResult:
    with SyncSessionLocal() as db:
        return ListIndexedReposResult(
            repositories=[
                IndexedRepo(
                    full_name=repo.full_name,
                    branch=ver.branch,
                    commit_sha=ver.commit_sha,
                    status=ver.status.value,
                    file_count=ver.file_count,
                    chunk_count=ver.chunk_count,
                    indexed_at=_iso(ver.indexed_at),
                )
                for repo, ver in indexed_repositories(db)
            ]
        )


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="search_codebase",
        description=(
            "Hybrid retrieval over an indexed repository: dense semantic search "
            "(pgvector embeddings) + lexical full-text (tsvector) + fuzzy symbol "
            "match (trigram), fused with reciprocal rank fusion. Returns the most "
            "relevant real code chunks with file path, line range and which "
            "retrievers matched. Use `list_indexed_repositories` first to see what "
            "is available."
        ),
    )
    async def search_codebase(
        repo: str,
        query: str,
        limit: int = 10,
        symbol_hints: list[str] | None = None,
        token_budget: int | None = None,
    ) -> SearchCodebaseResult:
        """
        Args:
            repo: Repository to search, as 'owner/name' or a unique substring of it.
            query: Natural-language description of the code you want to find.
            limit: Max chunks to return (1-40).
            symbol_hints: Optional identifier names to boost the symbol retriever.
            token_budget: Optional cap on total returned content tokens
                (defaults to the server's RETRIEVAL_TOKEN_BUDGET).
        """
        limit = max(1, min(limit, _MAX_LIMIT))
        try:
            return await anyio.to_thread.run_sync(
                _search_sync, repo, query, limit, symbol_hints, token_budget
            )
        except RepoNotFound as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(
        name="list_indexed_repositories",
        description=(
            "List repositories that have been connected to Sarathi and indexed "
            "(status 'ready'), with file/chunk counts. Call this to discover valid "
            "`repo` values for the other tools."
        ),
    )
    async def list_indexed_repositories() -> ListIndexedReposResult:
        return await anyio.to_thread.run_sync(_list_sync)

"""Genuine MCP end-to-end tests.

Spawns `python -m worker.mcp` as a real subprocess and drives it with a real MCP
`ClientSession` over stdio — the same transport Claude Desktop uses. No mocks.

- Protocol/schema checks always run.
- Real-data checks run only when a Postgres is reachable via DATABASE_URL_SYNC
  (CI provides one; locally they skip).
"""

from __future__ import annotations

import os
import sys

import pytest
import sqlalchemy as sa
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SYNC_URL = os.getenv(
    "DATABASE_URL_SYNC", "postgresql+psycopg://sarathi:sarathi@localhost:5433/sarathi"
)


def _db_ready() -> bool:
    """Reachable AND migrated — the api test suite drops the schema on teardown,
    so 'connects' isn't enough."""
    try:
        eng = sa.create_engine(_SYNC_URL, connect_args={"connect_timeout": 3})
        with eng.connect() as c:
            c.execute(sa.text("select 1 from repositories limit 0"))
        eng.dispose()
        return True
    except Exception:  # noqa: BLE001
        return False


DB = _db_ready()
requires_db = pytest.mark.skipif(
    not DB, reason="Postgres unreachable or schema not migrated (DATABASE_URL_SYNC)"
)


def _first_indexed_repo() -> str | None:
    if not DB:
        return None
    try:
        eng = sa.create_engine(_SYNC_URL)
        with eng.connect() as c:
            row = c.execute(
                sa.text(
                    "select r.full_name from repositories r "
                    "join repository_versions v on v.repository_id = r.id "
                    "where v.status = 'ready' order by r.full_name limit 1"
                )
            ).first()
        eng.dispose()
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        return None


INDEXED_REPO = _first_indexed_repo()
requires_indexed_repo = pytest.mark.skipif(
    INDEXED_REPO is None, reason="no indexed repository in this database"
)


def _server_params() -> StdioServerParameters:
    env = {
        **os.environ,
        "ENV": "test",
        "LLM_PROVIDER": "fake",
        "EMBEDDING_PROVIDER": "hash",  # deterministic, no API key
        "DATABASE_URL_SYNC": _SYNC_URL,
        "DATABASE_URL": _SYNC_URL.replace("+psycopg", "+asyncpg"),
    }
    return StdioServerParameters(
        command=sys.executable, args=["-m", "worker.mcp"], env=env, cwd=_REPO_ROOT
    )


async def test_lists_all_tools_with_schemas():
    async with stdio_client(_server_params()) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        resp = await session.list_tools()
        names = {t.name for t in resp.tools}
        assert names == {
            "search_codebase",
            "list_indexed_repositories",
            "get_repo_structure",
            "run_evaluation",
            "get_evaluation_result",
        }
        by_name = {t.name: t for t in resp.tools}

        sc = by_name["search_codebase"].inputSchema
        assert set(sc["required"]) == {"repo", "query"}
        assert "limit" in sc["properties"] and "symbol_hints" in sc["properties"]
        # structured output schema present -> Claude Desktop renders typed results
        assert by_name["search_codebase"].outputSchema is not None
        assert by_name["get_repo_structure"].inputSchema["required"] == ["repo"]
        assert by_name["get_evaluation_result"].inputSchema["required"] == ["evaluation_id"]


async def test_tool_error_is_reported_over_protocol_not_a_crash():
    """A failing tool call must come back as a normal MCP error result, not tear
    down the session."""
    async with stdio_client(_server_params()) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool(
            "search_codebase", {"repo": "definitely/not-a-real-repo-xyz", "query": "auth"}
        )
        assert result.isError is True
        text = " ".join(c.text for c in result.content if getattr(c, "type", None) == "text")
        assert text  # some diagnostic text came back
        # session still usable afterwards
        assert (await session.list_tools()).tools


@requires_db
async def test_unknown_repo_gives_a_helpful_message():
    async with stdio_client(_server_params()) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool(
            "search_codebase", {"repo": "definitely/not-a-real-repo-xyz", "query": "auth"}
        )
        assert result.isError is True
        text = " ".join(c.text for c in result.content if getattr(c, "type", None) == "text")
        assert "not-a-real-repo-xyz" in text or "No connected repository" in text


@requires_db
async def test_list_indexed_repositories_returns_real_rows():
    async with stdio_client(_server_params()) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool("list_indexed_repositories", {})
        assert result.isError is False
        data = result.structuredContent
        assert isinstance(data, dict) and "repositories" in data
        # environment-dependent: only assert shape, not that any repo exists
        for repo in data["repositories"]:
            assert repo["full_name"] and repo["status"] == "ready"
            assert isinstance(repo["chunk_count"], int)


@requires_indexed_repo
async def test_get_repo_structure_index_only():
    target = INDEXED_REPO
    async with stdio_client(_server_params()) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool(
            "get_repo_structure", {"repo": target, "include_analysis": False}
        )
        assert result.isError is False, result.content
        d = result.structuredContent
        assert d["repository"] == target
        assert d["file_count"] >= 1 and d["chunk_count"] >= 1
        assert d["languages"] and all(isinstance(v, int) for v in d["languages"].values())
        assert d["top_directories"] and d["top_directories"][0]["files"] >= 1
        assert d["analysis_source"] == "index-only"


@requires_indexed_repo
async def test_search_codebase_against_first_indexed_repo():
    target = INDEXED_REPO
    async with stdio_client(_server_params()) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool(
            "search_codebase", {"repo": target, "query": "database session", "limit": 5}
        )
        assert result.isError is False, result.content
        data = result.structuredContent
        assert data["repository"] == target
        assert data["returned"] >= 1
        first = data["matches"][0]
        assert first["path"] and first["content"]
        assert set(first["matched_by"]) <= {"vector", "keyword", "symbol"}

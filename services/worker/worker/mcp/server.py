"""Builds the Sarathi FastMCP server and registers every tool.

stdio transport: an MCP client (Claude Desktop, MCP Inspector, another agent)
spawns this as a subprocess and speaks JSON-RPC over stdin/stdout. All logging is
forced to **stderr** so it never corrupts that stream.
"""

from __future__ import annotations

import sys

from app.logging import configure_logging

# Must happen before anything else logs.
configure_logging(level="WARNING", json_output=False, stream=sys.stderr)

from app import __version__  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from worker.mcp.tools import evaluation, repo_structure, search_codebase  # noqa: E402

INSTRUCTIONS = f"""\
Sarathi MCP server v{__version__}.

Exposes Sarathi's real code-intelligence over MCP:
- list_indexed_repositories: what repositories are indexed and searchable.
- search_codebase: hybrid retrieval (semantic + lexical + symbol) over one repo.
- get_repo_structure: language/dir breakdown + a deterministic framework scan.
- run_evaluation / get_evaluation_result: enqueue + poll the benchmark harness.

Repositories are referenced by 'owner/name' (or a unique substring). Call
list_indexed_repositories first if you don't know a valid value. Every tool hits
the live Sarathi database; results are real, not synthetic.
"""


def build_server() -> FastMCP:
    mcp = FastMCP("sarathi", instructions=INSTRUCTIONS)
    search_codebase.register(mcp)
    repo_structure.register(mcp)
    evaluation.register(mcp)
    return mcp


mcp = build_server()

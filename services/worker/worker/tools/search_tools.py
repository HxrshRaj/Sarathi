"""Code search tools: literal/regex grep over the workspace, and semantic
retrieval over the indexed repository version.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from worker.tools.base import Tool, ToolError, ToolResult

_MAX_MATCHES = 80
_SKIP = {".git", "node_modules", ".venv", "__pycache__", "dist", "build", ".next"}


class SearchCodeArgs(BaseModel):
    pattern: str = Field(description="Python regular expression")
    path: str = Field(default="", description="limit search to this subtree")
    max_results: int = Field(default=40, le=_MAX_MATCHES)


class RetrieveArgs(BaseModel):
    query: str
    symbol_hints: list[str] = Field(default_factory=list)
    limit: int = Field(default=12, le=40)


def build_search_tools(workspace: Path, semantic_search) -> list[Tool]:  # noqa: ANN001
    def search_code(a: SearchCodeArgs) -> ToolResult:
        try:
            rx = re.compile(a.pattern)
        except re.error as exc:
            raise ToolError(f"Bad regex: {exc}") from exc
        base = workspace / a.path if a.path else workspace
        if not base.exists():
            raise ToolError(f"Path not found: {a.path}")
        hits: list[dict] = []
        for p in base.rglob("*"):
            if not p.is_file() or any(s in p.parts for s in _SKIP):
                continue
            try:
                text = p.read_text("utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    hits.append(
                        {"path": p.relative_to(workspace).as_posix(), "line": i, "text": line[:300]}
                    )
                    if len(hits) >= a.max_results:
                        return ToolResult(ok=True, data={"matches": hits, "truncated": True})
        return ToolResult(ok=True, data={"matches": hits, "truncated": False})

    def retrieve(a: RetrieveArgs) -> ToolResult:
        chunks = semantic_search(a.query, a.symbol_hints, a.limit)
        return ToolResult(ok=True, data={"chunks": chunks})

    return [
        Tool("search_code", "Regex search over repository files.", SearchCodeArgs, search_code),
        Tool(
            "retrieve",
            "Semantic + keyword retrieval over the indexed repository.",
            RetrieveArgs,
            retrieve,
        ),
    ]

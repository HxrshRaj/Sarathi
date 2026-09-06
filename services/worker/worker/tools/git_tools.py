from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from worker.git_ops import GitError, _run
from worker.tools.base import Tool, ToolResult


class NoArgs(BaseModel):
    pass


def build_git_tools(workspace: Path) -> list[Tool]:
    def git_diff(_a: NoArgs) -> ToolResult:
        try:
            patch = _run(["diff", "HEAD"], cwd=workspace)
            stat = _run(["diff", "--stat", "HEAD"], cwd=workspace)
        except GitError as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, data={"diff": patch[:60000], "stat": stat})

    return [Tool("git_diff", "Show the working-tree diff against HEAD.", NoArgs, git_diff)]

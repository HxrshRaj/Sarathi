"""Assemble the validated tool registry for a run."""

from __future__ import annotations

from dataclasses import dataclass

from worker.runtime.context import RunContext
from worker.runtime.schemas import RepoAnalysis
from worker.tools.base import ToolRegistry
from worker.tools.exec_tools import ExecContext, build_exec_tools, make_runner_or_none
from worker.tools.fs_tools import WorkspaceFS, build_fs_tools
from worker.tools.git_tools import build_git_tools
from worker.tools.search_tools import build_search_tools

_DEFAULT_TEST = {
    "pytest": ["pytest", "-q"],
    "npm test": ["npm", "test", "--silent"],
    "jest": ["npx", "jest", "--silent"],
    "vitest": ["npx", "vitest", "run"],
    "go test": ["go", "test", "./..."],
}
_DEFAULT_LINT = {
    "python": ["ruff", "check", "."],
    "javascript": ["npx", "eslint", "."],
    "typescript": ["npx", "tsc", "--noEmit"],
}
_DEFAULT_FORMAT = {
    "python": ["ruff", "format", "--check", "."],
    "javascript": ["npx", "prettier", "--check", "."],
    "typescript": ["npx", "prettier", "--check", "."],
}


@dataclass(slots=True)
class Toolset:
    registry: ToolRegistry
    fs: WorkspaceFS
    exec_ctx: ExecContext
    sandbox_available: bool


def _pick_test_command(analysis: RepoAnalysis) -> list[str] | None:
    for tf in analysis.test_frameworks:
        if tf in _DEFAULT_TEST:
            return _DEFAULT_TEST[tf]
    if analysis.test_commands:
        return analysis.test_commands[0].split()
    if "python" in analysis.languages:
        return ["pytest", "-q"]
    return None


def build_toolset(ctx: RunContext, analysis: RepoAnalysis, *, allow_mutations: bool) -> Toolset:
    primary_lang = analysis.languages[0] if analysis.languages else "python"
    fs = WorkspaceFS(ctx.workspace)
    runner = make_runner_or_none(primary_lang)
    exec_ctx = ExecContext(
        workspace=ctx.workspace,
        language=primary_lang,
        test_command=_pick_test_command(analysis),
        lint_command=_DEFAULT_LINT.get(primary_lang),
        format_command=_DEFAULT_FORMAT.get(primary_lang),
        runner=runner,
    )

    registry = ToolRegistry(allow_mutations=allow_mutations)
    registry.register_many(build_fs_tools(fs))
    registry.register_many(
        build_search_tools(
            ctx.workspace,
            lambda q, hints, limit: [
                {
                    "path": c.path,
                    "symbol": c.symbol,
                    "lines": [c.start_line, c.end_line],
                    "content": c.content,
                    "score": c.score,
                }
                for c in ctx.retrieve(q, hints, limit)
            ],
        )
    )
    registry.register_many(build_git_tools(ctx.workspace))
    registry.register_many(build_exec_tools(exec_ctx))
    return Toolset(registry, fs, exec_ctx, runner is not None)

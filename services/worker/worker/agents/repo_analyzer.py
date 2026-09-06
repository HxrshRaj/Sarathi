from __future__ import annotations

from worker.codeintel.languages import analyze_repo
from worker.llm.base import LLMMessage
from worker.runtime.context import RunContext
from worker.runtime.schemas import RepoAnalysis


def _file_tree_sample(ctx: RunContext, limit: int = 120) -> str:
    entries: list[str] = []
    for p in sorted(ctx.workspace.rglob("*")):
        if any(
            seg in {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}
            for seg in p.parts
        ):
            continue
        entries.append(p.relative_to(ctx.workspace).as_posix())
        if len(entries) >= limit:
            break
    return "\n".join(entries)


async def analyze(ctx: RunContext) -> RepoAnalysis:
    scan = analyze_repo(ctx.workspace)
    tree = _file_tree_sample(ctx)
    msg = (
        f"Deterministic scan:\n{scan}\n\n"
        f"File tree sample (first files):\n<repository_tree>\n{tree}\n</repository_tree>\n\n"
        "Produce the structured repository analysis."
    )
    analysis = await ctx.structured(
        "repo_analyzer",
        [LLMMessage(role="user", content=msg)],
        RepoAnalysis,
        purpose="repo_analyzer",
    )
    # Backfill from the deterministic scan so downstream steps never see empties.
    analysis.languages = analysis.languages or scan["languages"]
    analysis.package_managers = analysis.package_managers or scan["package_managers"]
    analysis.frameworks = analysis.frameworks or scan["frameworks"]
    analysis.test_frameworks = analysis.test_frameworks or scan["test_frameworks"]
    analysis.entry_points = analysis.entry_points or scan["entry_points"]
    analysis.important_directories = analysis.important_directories or scan["important_directories"]
    return analysis

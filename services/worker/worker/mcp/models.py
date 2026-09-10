"""Pydantic input/output schemas for the MCP tools.

FastMCP turns these into the JSON Schemas an MCP client (Claude Desktop, the MCP
Inspector, another agent) uses to discover and call the tools.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── search_codebase ──────────────────────────────────────────────────────────
class CodeMatch(BaseModel):
    path: str = Field(description="repository-relative file path")
    symbol: str | None = Field(default=None, description="function/class name if the chunk is one")
    kind: str = Field(description="chunk kind: function | class | method | module | block")
    start_line: int
    end_line: int
    score: float = Field(description="reciprocal-rank-fusion score across the three retrievers")
    matched_by: list[str] = Field(
        description="which retrievers hit this chunk: any of vector, keyword, symbol"
    )
    content: str = Field(description="the code chunk, secret-redacted at index time")


class SearchCodebaseResult(BaseModel):
    repository: str = Field(description="resolved repository full name (owner/name)")
    branch: str
    commit_sha: str
    indexed_at: str | None
    query: str
    returned: int
    matches: list[CodeMatch]


# ── get_repo_structure ───────────────────────────────────────────────────────
class DirEntry(BaseModel):
    path: str
    files: int
    languages: dict[str, int] = Field(default_factory=dict)


class RepoStructureResult(BaseModel):
    repository: str
    branch: str
    commit_sha: str
    indexed_at: str | None
    file_count: int
    chunk_count: int
    languages: dict[str, int] = Field(description="file count per language, indexed files only")
    top_directories: list[DirEntry] = Field(description="first-level dirs with file/lang counts")
    # from the real deterministic analyze_repo() scan (empty if the clone was skipped)
    package_managers: list[str] = []
    frameworks: list[str] = []
    test_frameworks: list[str] = []
    entry_points: list[str] = []
    important_directories: list[str] = []
    analysis_source: str = Field(
        description="'clone+analyze_repo' if the working tree was scanned, else 'index-only'"
    )
    notes: list[str] = []


# ── repositories discovery ───────────────────────────────────────────────────
class IndexedRepo(BaseModel):
    full_name: str
    branch: str
    commit_sha: str
    status: str
    file_count: int
    chunk_count: int
    indexed_at: str | None


class ListIndexedReposResult(BaseModel):
    repositories: list[IndexedRepo]


# ── run_evaluation / get_evaluation_result ───────────────────────────────────
class RunEvaluationResult(BaseModel):
    evaluation_id: str
    status: str
    benchmark_set: str
    model: str
    only: list[str] | None
    detail: str


class BenchmarkResult(BaseModel):
    benchmark_id: str
    passed: bool
    build_ok: bool
    lint_ok: bool
    tests_ok: bool
    security_ok: bool
    regression: bool
    repair_iterations: int
    judge_score: int | None
    latency_s: float
    cost_usd: float


class EvaluationResultOut(BaseModel):
    evaluation_id: str
    status: str
    model: str
    benchmark_set: str
    started_at: str | None
    finished_at: str | None
    task_success_rate: float | None
    test_pass_rate: float | None
    regression_rate: float | None
    security_violation_rate: float | None
    avg_latency_s: float | None
    avg_cost_usd: float | None
    has_regression: bool
    results: list[BenchmarkResult]

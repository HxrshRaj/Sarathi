"""Structured output contracts for each agent (forced-tool schemas)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepoAnalysis(BaseModel):
    languages: list[str] = []
    frameworks: list[str] = []
    package_managers: list[str] = []
    test_frameworks: list[str] = []
    entry_points: list[str] = []
    important_directories: list[str] = []
    build_commands: list[str] = []
    test_commands: list[str] = []
    architecture_summary: str = ""


class PlanStep(BaseModel):
    step: str
    rationale: str


class Plan(BaseModel):
    objective: str
    affected_components: list[str] = []
    files_to_modify: list[str] = []
    files_to_create: list[str] = []
    implementation_plan: list[PlanStep] = Field(default_factory=list)
    tests_required: list[str] = []
    risks: list[str] = []
    open_questions: list[str] = []


class RetrievalQueries(BaseModel):
    queries: list[str] = Field(min_length=1)
    symbols: list[str] = []
    path_fragments: list[str] = []


class CoderSummary(BaseModel):
    summary: str
    files_touched: list[str] = []
    followups: list[str] = []


class SecurityIssue(BaseModel):
    path: str | None = None
    line: int | None = None
    severity: str = Field(pattern="^(info|low|medium|high|critical)$")
    message: str
    fix: str


class SecurityReview(BaseModel):
    issues: list[SecurityIssue] = []


class ReviewResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    correctness: int = Field(ge=0, le=100)
    security: int = Field(ge=0, le=100)
    maintainability: int = Field(ge=0, le=100)
    testing: int = Field(ge=0, le=100)
    performance: int = Field(ge=0, le=100)
    blocking_issues: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    confidence: str = Field(default="medium", pattern="^(high|medium|low)$")


class PRArtifacts(BaseModel):
    branch_name: str
    commit_subject: str
    commit_body: str = ""
    pr_title: str
    pr_body: str

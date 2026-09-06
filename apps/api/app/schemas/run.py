from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import AgentName, RunStatus, SecuritySource, Severity, StepStatus
from app.schemas.common import ORMModel


class ToolCallOut(ORMModel):
    seq: int
    tool: str
    args_json: dict
    result_json: dict | None
    ok: bool
    error: str | None
    duration_ms: int


class AgentStepOut(ORMModel):
    seq: int
    agent: AgentName
    status: StepStatus
    started_at: datetime | None
    finished_at: datetime | None
    input_json: dict
    output_json: dict | None
    error: str | None
    prompt_version: str | None
    tool_calls: list[ToolCallOut] = []


class TestRunOut(ORMModel):
    phase: str
    command: str
    framework: str | None
    exit_code: int
    passed: int
    failed: int
    errors: int
    duration_ms: int
    stdout: str
    stderr: str


class SecurityFindingOut(ORMModel):
    source: SecuritySource
    severity: Severity
    rule_id: str | None
    path: str | None
    line: int | None
    message: str
    deterministic: bool


class ReviewOut(ORMModel):
    overall_score: int
    correctness: int
    security: int
    maintainability: int
    testing: int
    performance: int
    blocking_issues: list
    warnings: list
    suggestions: list
    production_ready: bool
    escalated_to_human: bool
    escalation_reason: str | None


class ModelUsageOut(ORMModel):
    provider: str
    model: str
    prompt_version: str | None
    purpose: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class RunReplayOut(ORMModel):
    id: uuid.UUID
    task_id: uuid.UUID
    status: RunStatus
    model: str
    autonomy: str
    correlation_id: str
    confidence: str | None
    summary: str | None
    error_category: str | None
    error_message: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[AgentStepOut] = []
    test_runs: list[TestRunOut] = []
    security_findings: list[SecurityFindingOut] = []
    review: ReviewOut | None = None
    model_usage: list[ModelUsageOut] = []

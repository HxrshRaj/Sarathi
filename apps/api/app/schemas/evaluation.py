from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EvaluationStatus
from app.schemas.common import ORMModel


class EvaluationRunIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    benchmark_set: str = Field(default="v1", max_length=128)
    model: str | None = None
    prompt_bundle: str = "active"
    baseline_evaluation_id: uuid.UUID | None = None
    comparison_group: str | None = None


class EvaluationResultOut(ORMModel):
    benchmark_id: str
    passed: bool
    build_ok: bool
    lint_ok: bool
    tests_ok: bool
    security_ok: bool
    regression: bool
    repair_iterations: int
    tool_failures: int
    latency_s: float
    cost_usd: float
    judge_score: int | None
    detail_json: dict


class EvaluationOut(ORMModel):
    id: uuid.UUID
    benchmark_set: str
    model: str
    prompt_bundle: str
    comparison_group: str | None
    status: EvaluationStatus
    started_at: datetime | None
    finished_at: datetime | None
    task_success_rate: float | None
    test_pass_rate: float | None
    regression_rate: float | None
    security_violation_rate: float | None
    avg_latency_s: float | None
    avg_cost_usd: float | None
    has_regression: bool
    created_at: datetime
    results: list[EvaluationResultOut] = []

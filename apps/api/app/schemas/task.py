from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AutonomyLevel, RunStatus, TaskStatus
from app.schemas.common import ORMModel


class TaskCreateIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    repository_id: uuid.UUID
    branch: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=8000)
    autonomy: AutonomyLevel = AutonomyLevel.SUPERVISED
    model: str | None = None
    max_iterations: int = Field(default=3, ge=1, le=10)
    run_evaluation: bool = False
    auto_create_pr: bool = False


class RunSummaryOut(ORMModel):
    id: uuid.UUID
    status: RunStatus
    confidence: str | None
    summary: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    error_category: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class TaskOut(ORMModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    branch: str
    title: str
    description: str
    autonomy: AutonomyLevel
    model: str
    max_iterations: int
    run_evaluation: bool
    auto_create_pr: bool
    status: TaskStatus
    created_at: datetime
    latest_run: RunSummaryOut | None = None


class FileChangeOut(ORMModel):
    path: str
    change_type: str
    diff: str
    before_content: str | None
    after_content: str | None
    lines_added: int
    lines_removed: int
    applied: bool


class DiffOut(BaseModel):
    run_id: uuid.UUID
    files: list[FileChangeOut]
    total_added: int
    total_removed: int


class ApproveIn(BaseModel):
    create_pr: bool = True
    confirm: bool = Field(description="Explicit user confirmation to push/open a PR")

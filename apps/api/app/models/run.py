from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PKMixin, TimestampMixin, pg_enum
from app.models.enums import (
    AgentName,
    AutonomyLevel,
    ChangeType,
    RunStatus,
    SecuritySource,
    Severity,
    StepStatus,
)


class AgentRun(Base, PKMixin, TimestampMixin):
    """One execution attempt of a task. Fully replayable from its children."""

    __tablename__ = "agent_runs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, name="run_status"), default=RunStatus.RUNNING, index=True
    )
    autonomy: Mapped[AutonomyLevel] = mapped_column(pg_enum(AutonomyLevel, name="autonomy_level"))
    model: Mapped[str] = mapped_column(String(128))
    workspace_path: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error_category: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    confidence: Mapped[str | None] = mapped_column(String(16))  # high | medium | low
    summary: Mapped[str | None] = mapped_column(Text)

    task: Mapped[Task] = relationship(back_populates="runs")  # noqa: F821
    steps: Mapped[list[AgentStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.seq"
    )
    file_changes: Mapped[list[FileChange]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentStep(Base, PKMixin, TimestampMixin):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("agent_run_id", "seq"),)

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    agent: Mapped[AgentName] = mapped_column(pg_enum(AgentName, name="agent_name"))
    status: Mapped[StepStatus] = mapped_column(
        pg_enum(StepStatus, name="step_status"), default=StepStatus.RUNNING
    )
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_json: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(64))

    run: Mapped[AgentRun] = relationship(back_populates="steps")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="step", cascade="all, delete-orphan", order_by="ToolCall.seq"
    )


class ToolCall(Base, PKMixin, TimestampMixin):
    __tablename__ = "tool_calls"

    agent_step_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(64))
    args_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSONB)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    step: Mapped[AgentStep] = relationship(back_populates="tool_calls")


class FileChange(Base, PKMixin, TimestampMixin):
    __tablename__ = "file_changes"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text)
    change_type: Mapped[ChangeType] = mapped_column(pg_enum(ChangeType, name="change_type"))
    before_content: Mapped[str | None] = mapped_column(Text)
    after_content: Mapped[str | None] = mapped_column(Text)
    diff: Mapped[str] = mapped_column(Text, default="")
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    lines_added: Mapped[int] = mapped_column(Integer, default=0)
    lines_removed: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[AgentRun] = relationship(back_populates="file_changes")


class TestRun(Base, PKMixin, TimestampMixin):
    __tablename__ = "test_runs"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    phase: Mapped[str] = mapped_column(String(32))  # baseline | post_change | repair_1 ...
    command: Mapped[str] = mapped_column(Text)
    framework: Mapped[str | None] = mapped_column(String(64))
    exit_code: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")


class SecurityFinding(Base, PKMixin, TimestampMixin):
    __tablename__ = "security_findings"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[SecuritySource] = mapped_column(pg_enum(SecuritySource, name="security_source"))
    severity: Mapped[Severity] = mapped_column(pg_enum(Severity, name="severity"))
    rule_id: Mapped[str | None] = mapped_column(String(128))
    path: Mapped[str | None] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    deterministic: Mapped[bool] = mapped_column(Boolean, default=True)


class Review(Base, PKMixin, TimestampMixin):
    __tablename__ = "reviews"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), unique=True
    )
    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    correctness: Mapped[int] = mapped_column(Integer, default=0)
    security: Mapped[int] = mapped_column(Integer, default=0)
    maintainability: Mapped[int] = mapped_column(Integer, default=0)
    testing: Mapped[int] = mapped_column(Integer, default=0)
    performance: Mapped[int] = mapped_column(Integer, default=0)
    blocking_issues: Mapped[list] = mapped_column(JSONB, default=list)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    suggestions: Mapped[list] = mapped_column(JSONB, default=list)
    production_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    escalated_to_human: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text)

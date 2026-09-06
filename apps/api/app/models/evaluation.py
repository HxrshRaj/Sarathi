from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PKMixin, TimestampMixin, pg_enum
from app.models.enums import EvaluationStatus


class Evaluation(Base, PKMixin, TimestampMixin):
    __tablename__ = "evaluations"

    benchmark_set: Mapped[str] = mapped_column(String(128))
    git_ref: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(128))
    prompt_bundle: Mapped[str] = mapped_column(String(128), default="active")
    comparison_group: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[EvaluationStatus] = mapped_column(
        pg_enum(EvaluationStatus, name="evaluation_status"), default=EvaluationStatus.QUEUED
    )
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    baseline_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="SET NULL")
    )

    task_success_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    test_pass_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    regression_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    security_violation_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    avg_latency_s: Mapped[float | None] = mapped_column(Numeric(10, 3))
    avg_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    has_regression: Mapped[bool] = mapped_column(Boolean, default=False)

    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvaluationResult(Base, PKMixin, TimestampMixin):
    __tablename__ = "evaluation_results"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    benchmark_id: Mapped[str] = mapped_column(String(128))
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    build_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    lint_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    tests_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    security_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    regression: Mapped[bool] = mapped_column(Boolean, default=False)
    repair_iterations: Mapped[int] = mapped_column(Integer, default=0)
    tool_failures: Mapped[int] = mapped_column(Integer, default=0)
    latency_s: Mapped[float] = mapped_column(Numeric(10, 3), default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    judge_score: Mapped[int | None] = mapped_column(Integer)
    detail_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    evaluation: Mapped[Evaluation] = relationship(back_populates="results")

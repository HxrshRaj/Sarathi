from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PKMixin, TimestampMixin
from app.models.enums import AutonomyLevel, TaskStatus


class Task(Base, PKMixin, TimestampMixin):
    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    repository_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repository_versions.id", ondelete="SET NULL")
    )
    branch: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(512))
    # The engineering request. UNTRUSTED as instructions to the agent (see THREAT_MODEL T1).
    description: Mapped[str] = mapped_column(Text)
    autonomy: Mapped[AutonomyLevel] = mapped_column(Enum(AutonomyLevel, name="autonomy_level"))
    model: Mapped[str] = mapped_column(String(128))
    max_iterations: Mapped[int] = mapped_column(Integer, default=3)
    run_evaluation: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_create_pr: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), default=TaskStatus.DRAFT, index=True
    )

    runs: Mapped[list[AgentRun]] = relationship(  # noqa: F821
        back_populates="task", cascade="all, delete-orphan", order_by="AgentRun.created_at.desc()"
    )

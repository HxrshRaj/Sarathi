from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PKMixin, TimestampMixin, pg_enum
from app.models.enums import PRState


class PullRequest(Base, PKMixin, TimestampMixin):
    __tablename__ = "pull_requests"

    task_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    branch: Mapped[str] = mapped_column(String(255))
    base: Mapped[str] = mapped_column(String(255))
    github_pr_number: Mapped[int | None] = mapped_column(Integer)
    github_pr_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[PRState] = mapped_column(pg_enum(PRState, name="pr_state"), default=PRState.DRAFT)
    commit_sha: Mapped[str | None] = mapped_column(String(40))

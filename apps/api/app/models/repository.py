from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PKMixin, TimestampMixin, TZDateTime, pg_enum
from app.models.enums import IndexStatus


class Repository(Base, PKMixin, TimestampMixin):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("user_id", "github_repo_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    github_repo_id: Mapped[int] = mapped_column(BigInteger)
    full_name: Mapped[str] = mapped_column(String(512))  # owner/name
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    private: Mapped[bool] = mapped_column(Boolean, default=True)
    clone_url: Mapped[str] = mapped_column(Text)

    versions: Mapped[list[RepositoryVersion]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="RepositoryVersion.created_at.desc()",
    )


class RepositoryVersion(Base, PKMixin, TimestampMixin):
    """A repo snapshot at a commit, plus its index status."""

    __tablename__ = "repository_versions"
    __table_args__ = (UniqueConstraint("repository_id", "commit_sha"),)

    repository_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    branch: Mapped[str] = mapped_column(String(255))
    commit_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[IndexStatus] = mapped_column(
        pg_enum(IndexStatus, name="index_status"), default=IndexStatus.PENDING
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    index_error: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[TZDateTime | None]

    repository: Mapped[Repository] = relationship(back_populates="versions")

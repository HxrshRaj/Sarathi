from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.models.base import Base, PKMixin, TimestampMixin
from app.models.enums import ChunkKind

_EMBED_DIM = get_settings().embedding_dim


class CodeFile(Base, PKMixin, TimestampMixin):
    __tablename__ = "code_files"
    __table_args__ = (UniqueConstraint("repository_version_id", "path"),)

    repository_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("repository_versions.id", ondelete="CASCADE"),
        index=True,
    )
    path: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha: Mapped[str] = mapped_column(String(64))
    symbol_count: Mapped[int] = mapped_column(Integer, default=0)


class CodeChunk(Base, PKMixin, TimestampMixin):
    """Retrieval unit. `content` is secret-redacted before insert."""

    __tablename__ = "code_chunks"

    repository_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("repository_versions.id", ondelete="CASCADE"),
        index=True,
    )
    code_file_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("code_files.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str | None] = mapped_column(String(512))
    kind: Mapped[ChunkKind] = mapped_column(Enum(ChunkKind, name="chunk_kind"))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBED_DIM))
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, LargeBinary, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PKMixin, TimestampMixin, pg_enum
from app.models.enums import AutonomyLevel


class User(Base, PKMixin, TimestampMixin):
    __tablename__ = "users"

    github_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    login: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    default_autonomy: Mapped[AutonomyLevel] = mapped_column(
        pg_enum(AutonomyLevel, name="autonomy_level"), default=AutonomyLevel.SUPERVISED
    )
    monthly_cost_cap_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))

    identity: Mapped[GithubIdentity | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class GithubIdentity(Base, PKMixin, TimestampMixin):
    """Encrypted OAuth token. Never serialized by any API response."""

    __tablename__ = "github_identities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    token_expires_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(back_populates="identity")


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # opaque cookie value
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)

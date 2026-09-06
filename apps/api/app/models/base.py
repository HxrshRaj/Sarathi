"""Declarative base + shared column mixins."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Enum, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Every timestamp column is `timestamptz`. App code always writes tz-aware UTC
# datetimes; asyncpg rejects those against a naive column.
TZDateTime = Annotated[datetime, mapped_column(DateTime(timezone=True))]

# Predictable constraint names -> clean Alembic autogenerate diffs.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(py_enum: type[enum.Enum], *, name: str) -> Enum:
    """Postgres native ENUM whose labels are the enum *values* (lowercase
    StrEnum values), not the member names. Keeps ORM writes, raw SQL, and the
    JSON the API emits all on the same strings.
    """
    return Enum(
        py_enum,
        name=name,
        native_enum=True,
        values_callable=lambda e: [str(m.value) for m in e],
    )


class PKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

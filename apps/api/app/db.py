"""Async SQLAlchemy engine/session wiring.

Sync engine (psycopg) is exposed too — Alembic and the Celery worker use it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

_settings = get_settings()


def _async_url(url: str) -> str:
    """Force-disable asyncpg's prepared-statement cache in the URL — it breaks
    behind a transaction-mode pooler (Neon's `-pooler` endpoint / PgBouncer).
    Harmless for direct connections."""
    if "postgresql+asyncpg" in url and "prepared_statement_cache_size" not in url:
        url += ("&" if "?" in url else "?") + "prepared_statement_cache_size=0"
    return url


async_engine: AsyncEngine = create_async_engine(
    _async_url(_settings.database_url),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=280,  # Neon drops idle connections after ~5 min
    connect_args={"statement_cache_size": 0},
    future=True,
)

AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

sync_engine = create_engine(_settings.database_url_sync, pool_pre_ping=True, future=True)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one transaction-scoped session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping() -> bool:
    from sqlalchemy import text

    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True

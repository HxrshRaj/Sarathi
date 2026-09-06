"""Test fixtures.

DB-backed tests need a reachable Postgres (with pgvector). If `DATABASE_URL_SYNC`
is unreachable the whole DB-dependent suite is skipped with a clear reason — CI
provides a `pgvector/pgvector:pg16` service so they always run there.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from app.config import get_settings


def _db_reachable() -> bool:
    try:
        eng = sa.create_engine(
            get_settings().database_url_sync, connect_args={"connect_timeout": 3}
        )
        with eng.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:  # noqa: BLE001
        return False


DB_AVAILABLE = _db_reachable()
requires_db = pytest.mark.skipif(
    not DB_AVAILABLE, reason="Postgres (DATABASE_URL_SYNC) not reachable"
)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    if not DB_AVAILABLE:
        yield
        return
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    if not DB_AVAILABLE:
        return
    from app.db import sync_engine
    from app.models.base import Base

    with sync_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in {"prompt_versions"}:
                continue
            conn.execute(table.delete())


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

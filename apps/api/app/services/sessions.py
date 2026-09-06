"""Server-side sessions. The cookie value is an opaque random id; all state is in DB."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import Session as SessionModel
from app.models.user import User


async def create_session(
    db: AsyncSession, user: User, *, user_agent: str | None, ip: str | None
) -> SessionModel:
    s = get_settings()
    row = SessionModel(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=s.session_ttl_hours),
        user_agent=(user_agent or "")[:512] or None,
        ip=ip,
    )
    db.add(row)
    await db.flush()
    return row


async def resolve_session(db: AsyncSession, session_id: str) -> User | None:
    row = await db.get(SessionModel, session_id)
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        return None
    return await db.get(User, row.user_id)


async def revoke_session(db: AsyncSession, session_id: str) -> None:
    row = await db.get(SessionModel, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await db.flush()


async def get_or_create_dev_user(db: AsyncSession) -> User:
    """Only reachable when DEV_AUTH_BYPASS is on (refused in production by config)."""
    existing = await db.scalar(select(User).where(User.github_user_id == 0))
    if existing:
        return existing
    user = User(github_user_id=0, login="dev", name="Local Dev", avatar_url=None)
    db.add(user)
    await db.flush()
    return user

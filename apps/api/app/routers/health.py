from __future__ import annotations

from fastapi import APIRouter
from redis.asyncio import Redis

from app import __version__
from app.config import get_settings
from app.db import ping as db_ping
from app.schemas.common import Health

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok", version=__version__)


@router.get("/health/ready", response_model=Health)
async def ready() -> Health:
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        await db_ping()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        r = Redis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"

    _llm_key = {
        "fake": True,
        "gemini": bool(settings.gemini_api_key),
        "anthropic": bool(settings.anthropic_api_key),
    }.get(settings.llm_provider, False)
    checks["llm_provider"] = settings.llm_provider
    checks["llm_key"] = "present" if _llm_key else "missing"
    checks["embedding_provider"] = settings.embedding_provider
    checks["github_oauth"] = (
        "configured" if settings.github_client_id and settings.github_client_secret else "unset"
    )

    overall = (
        "ok"
        if all(v == "ok" for k, v in checks.items() if k in {"database", "redis"})
        else "degraded"
    )
    return Health(status=overall, version=__version__, checks=checks)

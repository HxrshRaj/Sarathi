"""Run event bus: Redis pub/sub for live fan-out + a bounded replay list.

Producer (worker) calls `publish()`. Consumers (API SSE) call `history()` for
backfill then `subscribe()` for the live tail. Persisted `agent_steps` remain the
source of truth; this is the low-latency transport.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.config import get_settings
from app.schemas.events import RunEvent

_REPLAY_MAX = 2000
_REPLAY_TTL_S = 60 * 60 * 6


def _keys(run_id: str) -> tuple[str, str]:
    return f"run:{run_id}:events", f"run:{run_id}:channel"


_pool: Redis | None = None


def _client() -> Redis:
    global _pool
    if _pool is None:
        _pool = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _pool


async def publish(event: RunEvent) -> None:
    payload = event.model_dump_json()
    list_key, channel = _keys(str(event.run_id))
    pipe = _client().pipeline()
    pipe.rpush(list_key, payload)
    pipe.ltrim(list_key, -_REPLAY_MAX, -1)
    pipe.expire(list_key, _REPLAY_TTL_S)
    pipe.publish(channel, payload)
    await pipe.execute()


async def history(run_id: str, *, after_id: str | None = None) -> list[RunEvent]:
    list_key, _ = _keys(run_id)
    raw = await _client().lrange(list_key, 0, -1)
    events = [RunEvent.model_validate_json(r) for r in raw]
    if after_id is not None:
        events = [e for e in events if e.id > after_id]
    return events


async def subscribe(run_id: str) -> AsyncIterator[RunEvent]:
    _, channel = _keys(run_id)
    pubsub = _client().pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            yield RunEvent.model_validate(json.loads(message["data"]))
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

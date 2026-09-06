"""Sync run-event publisher (worker side).

Mirrors app.services.events wire format so the API's async SSE relay and the web
client consume one contract. Persisted agent_steps remain the source of truth.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime

import redis
from app.config import get_settings

_REPLAY_MAX = 2000
_REPLAY_TTL_S = 60 * 60 * 6

_client: redis.Redis | None = None


def _r() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


class EventEmitter:
    def __init__(self, run_id: str, task_id: str) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self._seq = 0

    def emit(
        self,
        type_: str,
        data: dict | None = None,
        *,
        agent: str | None = None,
        step_seq: int | None = None,
    ) -> None:
        self._seq += 1
        event = {
            "id": f"{int(time.time() * 1000):013d}-{self._seq:04d}",
            "run_id": self.run_id,
            "task_id": self.task_id,
            "type": type_,
            "at": datetime.now(UTC).isoformat(),
            "agent": agent,
            "step_seq": step_seq,
            "data": data or {},
        }
        payload = json.dumps(event)
        list_key = f"run:{self.run_id}:events"
        channel = f"run:{self.run_id}:channel"
        try:
            pipe = _r().pipeline()
            pipe.rpush(list_key, payload)
            pipe.ltrim(list_key, -_REPLAY_MAX, -1)
            pipe.expire(list_key, _REPLAY_TTL_S)
            pipe.publish(channel, payload)
            pipe.execute()
        except redis.RedisError:
            pass  # event transport is best-effort; DB rows are authoritative

    def cancelled(self) -> bool:
        try:
            return _r().get(f"run:{self.run_id}:cancel") == "1"
        except redis.RedisError:
            return False


def new_correlation_id() -> str:
    return f"run-{datetime.now(UTC):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"

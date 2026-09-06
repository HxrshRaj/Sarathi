"""Redis token-bucket rate limiting. Fail-open if Redis is unavailable (logged)."""

from __future__ import annotations

import time

from redis.asyncio import Redis

from app.config import get_settings
from app.errors import RateLimited
from app.logging import get_logger

log = get_logger("ratelimit")

_redis: Redis | None = None

# name -> (max_tokens, refill_per_second)
LIMITS: dict[str, tuple[int, float]] = {
    "task_create": (10, 10 / 60),
    "task_run": (20, 20 / 60),
    "repo_index": (5, 5 / 60),
    "task_approve": (10, 10 / 60),
    "evaluation_run": (3, 3 / 60),
}

_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])
if tokens == nil then tokens = capacity; ts = now end
tokens = math.min(capacity, tokens + (now - ts) * refill)
local allowed = 0
if tokens >= 1 then tokens = tokens - 1; allowed = 1 end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / refill) + 1)
return {allowed, tostring(tokens)}
"""


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def enforce(bucket: str, identity: str) -> None:
    capacity, refill = LIMITS[bucket]
    key = f"rl:{bucket}:{identity}"
    try:
        allowed, _tokens = await _client().eval(_LUA, 1, key, capacity, refill, time.time())
    except Exception as exc:  # noqa: BLE001 - fail open, but record it
        log.warning("ratelimit_unavailable", bucket=bucket, error=str(exc))
        return
    if int(allowed) == 0:
        raise RateLimited(retry_after_s=max(1, int(1 / refill)))

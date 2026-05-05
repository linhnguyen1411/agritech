import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    value = await r.get(key)
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


async def cache_set(key: str, value: Any, ttl: int = settings.REDIS_CACHE_TTL) -> None:
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value, default=str))


async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


async def cache_delete_pattern(pattern: str) -> None:
    r = await get_redis()
    keys: list[str] = await r.keys(pattern)
    if keys:
        await r.delete(*keys)


# ── Rate-limit helper (sliding window via sorted set) ─────────────────────────

async def check_rate_limit(
    identifier: str,
    limit: int = settings.RATE_LIMIT_PER_MINUTE,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """Returns (allowed, remaining).  Uses a sorted-set sliding window."""
    import time

    r = await get_redis()
    key = f"rate:{identifier}"
    now = time.time()
    window_start = now - window_seconds

    pipe = r.pipeline()
    await pipe.zremrangebyscore(key, "-inf", window_start)  # evict old
    await pipe.zadd(key, {str(now): now})
    await pipe.zcard(key)
    await pipe.expire(key, window_seconds)
    results = await pipe.execute()

    count: int = results[2]
    allowed = count <= limit
    remaining = max(0, limit - count)
    return allowed, remaining

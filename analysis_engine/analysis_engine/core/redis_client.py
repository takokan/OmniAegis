from __future__ import annotations

from functools import lru_cache
from typing import Any

from upstash_redis.asyncio import Redis

from .config import Settings


@lru_cache(maxsize=1)
def get_redis(settings: Settings) -> Redis:
    # Upstash REST-backed Redis client (supports Streams commands).
    return Redis(url=settings.upstash_redis_rest_url, token=settings.upstash_redis_rest_token)


async def ensure_consumer_group(
    redis: Redis,
    *,
    stream_key: str,
    group_name: str,
) -> None:
    # XGROUP CREATE <key> <groupname> $ MKSTREAM
    try:
        await redis.execute("XGROUP", "CREATE", stream_key, group_name, "$", "MKSTREAM")
    except Exception as exc:
        # Upstash returns errors as exceptions; treat BUSYGROUP as idempotent success.
        if "BUSYGROUP" not in str(exc):
            raise


async def xlen(redis: Redis, stream_key: str) -> int:
    value: Any = await redis.execute("XLEN", stream_key)
    try:
        return int(value)
    except Exception:
        return 0


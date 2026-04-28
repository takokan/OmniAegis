from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

import asyncpg
from neo4j import AsyncDriver, AsyncGraphDatabase
from redis.asyncio import Redis

from .config import get_settings

try:  # optional: Upstash REST redis (cloud)
    from upstash_redis.asyncio import Redis as UpstashRedis
except Exception:  # pragma: no cover
    UpstashRedis = None  # type: ignore[assignment]


class _UpstashRedisAdapter:
    """Compatibility layer to mimic the subset of redis-py API used by this repo.

    Upstash REST SDK exposes a generic `execute(...)` interface. Many parts of this
    codebase expect `redis.asyncio.Redis`-style convenience methods.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def execute(self, *args: Any) -> Any:
        # upstash_redis.asyncio.Redis.execute expects a single command list.
        # Accept varargs here so callers can keep redis-py-like usage.
        if len(args) == 1 and isinstance(args[0], list):
            command = args[0]
        else:
            command = list(args)
        return await self._client.execute(command)

    async def ping(self) -> bool:
        resp = await self.execute("PING")
        return resp in (True, "PONG", b"PONG")

    async def xgroup_create(self, *, name: str, groupname: str, id: str, mkstream: bool = False) -> Any:
        cmd: list[Any] = ["XGROUP", "CREATE", name, groupname, id]
        if mkstream:
            cmd.append("MKSTREAM")
        return await self.execute(*cmd)

    async def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> Any:
        if len(streams) != 1:
            raise ValueError("Upstash adapter supports a single stream per call")
        (stream_key, stream_id), = streams.items()
        cmd: list[Any] = ["XREADGROUP", "GROUP", groupname, consumername]
        if count is not None:
            cmd.extend(["COUNT", int(count)])
        if block is not None:
            cmd.extend(["BLOCK", int(block)])
        cmd.extend(["STREAMS", stream_key, stream_id])
        return await self.execute(*cmd)

    async def xack(self, stream: str, group: str, message_id: str) -> Any:
        return await self.execute("XACK", stream, group, message_id)

    async def xadd(self, stream: str, fields: dict[str, Any], id: str = "*") -> Any:
        # Flatten mapping into varargs
        args: list[Any] = []
        for k, v in fields.items():
            args.extend([k, v])
        return await self.execute("XADD", stream, id, *args)

    async def xrevrange(
        self,
        stream: str,
        max_id: str = "+",
        min_id: str = "-",
        count: int | None = None,
    ) -> Any:
        cmd: list[Any] = ["XREVRANGE", stream, max_id, min_id]
        if count is not None:
            cmd.extend(["COUNT", int(count)])
        resp = await self.execute(*cmd)
        return resp or []

    async def zadd(self, key: str, mapping: dict[str, float]) -> Any:
        args: list[Any] = []
        for member, score in mapping.items():
            args.extend([float(score), member])
        return await self.execute("ZADD", key, *args)

    async def zrevrange(self, key: str, start: int, stop: int, withscores: bool = False) -> Any:
        cmd: list[Any] = ["ZREVRANGE", key, int(start), int(stop)]
        if withscores:
            cmd.append("WITHSCORES")
        resp = await self.execute(*cmd)
        if not withscores:
            return resp
        # Normalize to list[(member, score)] as redis-py does.
        out: list[tuple[Any, float]] = []
        if isinstance(resp, list):
            for i in range(0, len(resp) - 1, 2):
                out.append((resp[i], float(resp[i + 1])))
        return out


_redis_client: Redis | None = None
_postgres_pool: asyncpg.Pool | None = None
_neo4j_driver: AsyncDriver | None = None
_clients_lock = asyncio.Lock()


def _settings() -> Any:
    return get_settings()


async def get_redis_client() -> Redis:
    """Return a singleton Redis asyncio client backed by a shared connection pool."""
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    async with _clients_lock:
        if _redis_client is None:
            settings = _settings()
            import os

            # Prefer Upstash REST credentials when present (cloud-first).
            upstash_url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
            upstash_token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()

            if UpstashRedis is not None and upstash_url and upstash_token:
                client = UpstashRedis(url=upstash_url, token=upstash_token)
                _redis_client = _UpstashRedisAdapter(client)  # type: ignore[assignment]
            else:
                _redis_client = Redis.from_url(
                    str(settings.redis_url),
                    decode_responses=True,
                    health_check_interval=30,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                )

    return _redis_client


async def get_postgres_pool() -> asyncpg.Pool:
    """Return a singleton asyncpg connection pool for Supabase/PostgreSQL."""
    global _postgres_pool

    if _postgres_pool is not None:
        return _postgres_pool

    async with _clients_lock:
        if _postgres_pool is None:
            _postgres_pool = await asyncpg.create_pool(
                dsn=str(_settings().database_url),
                min_size=1,
                max_size=10,
                max_inactive_connection_lifetime=300,
                timeout=10,
                command_timeout=10,
            )

    return _postgres_pool


async def get_neo4j_driver() -> AsyncDriver:
    """Return a singleton Neo4j async driver configured for AuraDB."""
    global _neo4j_driver

    if _neo4j_driver is not None:
        return _neo4j_driver

    async with _clients_lock:
        if _neo4j_driver is None:
            settings = _settings()
            _neo4j_driver = AsyncGraphDatabase.driver(
                str(settings.neo4j_uri),
                auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
                max_connection_pool_size=50,
                connection_timeout=10,
                keep_alive=True,
            )

    return _neo4j_driver


async def init_db_clients() -> None:
    """Warm up all shared clients at application startup."""
    await asyncio.gather(get_redis_client(), get_postgres_pool(), get_neo4j_driver())


async def _run_with_context(label: str, coroutine: Awaitable[Any]) -> str | None:
    try:
        await coroutine
        return None
    except Exception as exc:  # pragma: no cover - defensive for infra/runtime variance
        return f"{label} connection failed: {exc!s}"


async def check_connections() -> None:
    """Validate connectivity for Redis, PostgreSQL, and Neo4j.

    Raises:
        RuntimeError: when one or more connectivity checks fail.
    """

    redis_client = await get_redis_client()
    postgres_pool = await get_postgres_pool()
    neo4j_driver = await get_neo4j_driver()

    async def _check_redis() -> None:
        pong = await redis_client.ping()
        if pong is not True:
            raise RuntimeError("unexpected PING response")

    async def _check_postgres() -> None:
        async with postgres_pool.acquire() as conn:
            value = await conn.fetchval("SELECT 1")
            if value != 1:
                raise RuntimeError("unexpected SELECT 1 result")

    async def _check_neo4j() -> None:
        await neo4j_driver.verify_connectivity()
        async with neo4j_driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            if record is None or record.get("ok") != 1:
                raise RuntimeError("unexpected Neo4j query result")

    failures = await asyncio.gather(
        _run_with_context("Redis", _check_redis()),
        _run_with_context("PostgreSQL", _check_postgres()),
        _run_with_context("Neo4j", _check_neo4j()),
    )

    errors = [error for error in failures if error is not None]
    if errors:
        raise RuntimeError(" | ".join(errors))


async def close_db_clients() -> None:
    """Gracefully close all singleton clients."""
    global _redis_client, _postgres_pool, _neo4j_driver

    async with _clients_lock:
        if _redis_client is not None:
            await _redis_client.aclose()
            _redis_client = None

        if _postgres_pool is not None:
            await _postgres_pool.close()
            _postgres_pool = None

        if _neo4j_driver is not None:
            await _neo4j_driver.close()
            _neo4j_driver = None

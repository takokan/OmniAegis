from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

import asyncpg
from neo4j import AsyncDriver, AsyncGraphDatabase
from redis.asyncio import Redis

from .config import get_settings


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
            _redis_client = Redis.from_url(
                str(_settings().redis_url),
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

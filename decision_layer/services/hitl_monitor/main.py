from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

try:
    from decision_layer.shared import close_db_clients, get_neo4j_driver, get_postgres_pool, get_redis_client
except ModuleNotFoundError:  # pragma: no cover
    from shared import close_db_clients, get_neo4j_driver, get_postgres_pool, get_redis_client


logger = logging.getLogger(__name__)

HITL_QUEUE_KEY = "sentinel:hitl:queue"
HITL_RETRY_LIMIT = 3


async def handle_hitl_item_async(item_payload: dict[str, Any]) -> None:
    """Placeholder HITL business logic.

    Keep this async and I/O-only. For CPU-heavy logic, offload via `asyncio.to_thread`.
    """

    pg_pool = await get_postgres_pool()
    neo4j_driver = await get_neo4j_driver()

    # Example: use shared clients non-blockingly.
    async with pg_pool.acquire() as conn:
        await conn.execute("SELECT 1")

    async with neo4j_driver.session() as session:
        await session.run("RETURN 1 AS ok")

    await asyncio.sleep(0)


class HITLQueueWorker:
    """Async worker that drains `sentinel:hitl:queue` (Redis Sorted Set)."""

    def __init__(
        self,
        poll_interval_seconds: float = 0.5,
        retry_limit: int = HITL_RETRY_LIMIT,
    ) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self.retry_limit = retry_limit
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="sentinel-hitl-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        redis_client = await get_redis_client()

        while not self._stop_event.is_set():
            try:
                popped = await redis_client.zpopmax(HITL_QUEUE_KEY, count=1)
                if not popped:
                    await asyncio.sleep(self.poll_interval_seconds)
                    continue

                member, score = popped[0]
                payload = self._decode_payload(member)
                payload.setdefault("priority_score", float(score))

                await self._process_or_requeue(redis_client=redis_client, payload=payload, score=float(score))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - network/runtime dependent
                logger.exception("HITL loop error: %s", exc)
                await asyncio.sleep(1.0)

    def _decode_payload(self, member: Any) -> dict[str, Any]:
        if isinstance(member, bytes):
            member = member.decode("utf-8", errors="replace")

        if isinstance(member, str):
            try:
                parsed = json.loads(member)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"asset_id": member}

        return {"asset_id": str(member)}

    async def _process_or_requeue(self, redis_client: Any, payload: dict[str, Any], score: float) -> None:
        retry_count = int(payload.get("retry_count", 0))

        try:
            await handle_hitl_item_async(payload)
            logger.info("HITL item processed asset_id=%s", payload.get("asset_id"))
        except Exception as exc:  # pragma: no cover - business/runtime dependent
            retry_count += 1
            payload["retry_count"] = retry_count
            payload["last_error"] = str(exc)
            payload["failed_at"] = datetime.now(UTC).isoformat()

            if retry_count <= self.retry_limit:
                # Re-queue with slight priority increase to prevent starvation.
                await redis_client.zadd(HITL_QUEUE_KEY, {json.dumps(payload): score + 0.0001})
                logger.warning(
                    "HITL item re-queued asset_id=%s retries=%s error=%s",
                    payload.get("asset_id"),
                    retry_count,
                    exc,
                )
                return

            logger.error(
                "HITL item dropped after retries asset_id=%s retries=%s error=%s",
                payload.get("asset_id"),
                retry_count,
                exc,
            )


async def run_hitl_monitor() -> None:
    worker = HITLQueueWorker(
        poll_interval_seconds=float(os.getenv("HITL_POLL_INTERVAL_SECONDS", "0.5")),
        retry_limit=int(os.getenv("HITL_RETRY_LIMIT", str(HITL_RETRY_LIMIT))),
    )

    await worker.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await worker.stop()
        await close_db_clients()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    start = time.perf_counter()
    try:
        asyncio.run(run_hitl_monitor())
    finally:
        logger.info("HITL monitor exited after %.2fs", time.perf_counter() - start)

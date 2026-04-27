from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError

try:
    from decision_layer.services.ml_engine import InferenceModelLoader
    from decision_layer.shared import close_db_clients, get_redis_client
except ModuleNotFoundError:  # pragma: no cover
    from services.ml_engine import InferenceModelLoader
    from shared import close_db_clients, get_redis_client


logger = logging.getLogger(__name__)

STREAM_KEY = "sentinel:ingest:stream"
GROUP_NAME = "sentinel:ingest:group"
DLQ_STREAM_KEY = "sentinel:ingest:dlq"
HITL_QUEUE_KEY = "sentinel:hitl:queue"


class _InferenceRuntime:
    def __init__(self) -> None:
        self.loader = InferenceModelLoader(models_dir=os.getenv("MODELS_DIR", "./models"), device="cpu")
        self.semantic_modules = self.loader.load_semantic_modules()
        self.rights_gnn = self.loader.load_rights_gnn()


_INFERENCE_RUNTIME: _InferenceRuntime | None = None
_INFERENCE_LOCK = asyncio.Lock()


async def _get_inference_runtime() -> _InferenceRuntime:
    global _INFERENCE_RUNTIME

    if _INFERENCE_RUNTIME is not None:
        return _INFERENCE_RUNTIME

    async with _INFERENCE_LOCK:
        if _INFERENCE_RUNTIME is None:
            _INFERENCE_RUNTIME = await asyncio.to_thread(_InferenceRuntime)
    return _INFERENCE_RUNTIME


def _inference_sync(asset_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Synchronous adapter for existing ML modules (executed in thread pool)."""
    runtime = _INFERENCE_RUNTIME
    if runtime is None:
        raise RuntimeError("Inference runtime is not initialized")

    # Placeholder integration contract:
    # 1) Build feature tensor/embedding using existing preprocessing.
    # 2) Run `runtime.rights_gnn(...)` and derive policy score/decision.
    # 3) Return normalized decision payload.
    # Keep this shape stable so downstream HITL + audit stages can consume it.
    confidence = float(metadata.get("confidence_hint", 0.5))
    decision = "hitl" if confidence < 0.75 else "allow"
    return {
        "asset_id": asset_id,
        "decision": decision,
        "confidence": confidence,
        "model_mode": runtime.semantic_modules.get("mode", "unknown"),
    }


async def run_ml_inference_async(asset_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    await _get_inference_runtime()
    return await asyncio.to_thread(_inference_sync, asset_id, metadata)


async def process_asset_async(asset_id: str, metadata: dict[str, Any]) -> None:
    """Placeholder asset processing hook for downstream ingestion logic."""
    inference = await run_ml_inference_async(asset_id=asset_id, metadata=metadata)

    if inference.get("decision") == "hitl":
        redis_client = await get_redis_client()
        priority = float(1.0 - float(inference.get("confidence", 0.5)))
        hitl_payload = {
            "asset_id": asset_id,
            "metadata": metadata,
            "inference": inference,
            "queued_at": datetime.now(UTC).isoformat(),
        }
        await redis_client.zadd(HITL_QUEUE_KEY, {json.dumps(hitl_payload): priority})

    logger.info("Processed asset_id=%s decision=%s", asset_id, inference.get("decision"))


class RedisStreamIngestor:
    """Async Redis Streams consumer-group worker for Sentinel ingestion."""

    def __init__(
        self,
        redis_client: Redis,
        stream_key: str = STREAM_KEY,
        group_name: str = GROUP_NAME,
        consumer_name: str | None = None,
        max_retries: int = 3,
        read_count: int = 16,
        block_ms: int = 5000,
        idle_sleep_seconds: float = 0.25,
    ) -> None:
        self.redis = redis_client
        self.stream_key = stream_key
        self.group_name = group_name
        self.consumer_name = consumer_name or f"ingestor-{uuid4().hex[:8]}"
        self.max_retries = max_retries
        self.read_count = read_count
        self.block_ms = block_ms
        self.idle_sleep_seconds = idle_sleep_seconds

        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def ensure_consumer_group(self) -> None:
        """Create consumer group if missing; ignore BUSYGROUP for idempotency."""
        try:
            await self.redis.xgroup_create(
                name=self.stream_key,
                groupname=self.group_name,
                id="$",
                mkstream=True,
            )
            logger.info(
                "Created Redis stream group stream=%s group=%s",
                self.stream_key,
                self.group_name,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def start(self) -> None:
        if self._task is not None:
            return
        await self.ensure_consumer_group()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._consume_loop(), name="sentinel-ingestor-consumer")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _consume_loop(self) -> None:
        logger.info(
            "Ingestor consumer started stream=%s group=%s consumer=%s",
            self.stream_key,
            self.group_name,
            self.consumer_name,
        )

        while not self._stop_event.is_set():
            try:
                results = await self.redis.xreadgroup(
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=self.read_count,
                    block=self.block_ms,
                )

                if not results:
                    await asyncio.sleep(self.idle_sleep_seconds)
                    continue

                for _stream, entries in results:
                    for message_id, fields in entries:
                        await self._handle_message(message_id=message_id, fields=fields)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - runtime/network dependent
                logger.exception("Redis stream consumer loop error: %s", exc)
                await asyncio.sleep(1.0)

    async def _handle_message(self, message_id: str, fields: dict[str, Any]) -> None:
        asset_id = str(fields.get("asset_id", "")).strip()
        if not asset_id:
            await self._handle_failure(
                message_id=message_id,
                fields=fields,
                error=ValueError("missing required field: asset_id"),
            )
            return

        metadata = self._extract_metadata(fields)

        try:
            await process_asset_async(asset_id=asset_id, metadata=metadata)
            await self.redis.xack(self.stream_key, self.group_name, message_id)
        except Exception as exc:  # pragma: no cover - business logic/runtime dependent
            await self._handle_failure(message_id=message_id, fields=fields, error=exc)

    def _extract_metadata(self, fields: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "filename": fields.get("filename"),
            "content_type": fields.get("content_type"),
            "source": fields.get("source"),
            "storage_url": fields.get("storage_url"),
            "uploaded_at": fields.get("uploaded_at"),
        }

        for key, value in fields.items():
            if key not in metadata and key not in {"asset_id", "retry_count", "last_error", "failed_at"}:
                metadata[key] = value

        return {k: v for k, v in metadata.items() if v is not None}

    async def _handle_failure(self, message_id: str, fields: dict[str, Any], error: Exception) -> None:
        retry_count = int(fields.get("retry_count", 0)) + 1
        payload = dict(fields)
        payload["retry_count"] = str(retry_count)
        payload["last_error"] = str(error)
        payload["failed_at"] = datetime.now(UTC).isoformat()

        if retry_count <= self.max_retries:
            try:
                await self.redis.xadd(self.stream_key, payload)
                await self.redis.xack(self.stream_key, self.group_name, message_id)
                logger.warning(
                    "Re-queued ingest message id=%s retry_count=%s error=%s",
                    message_id,
                    retry_count,
                    error,
                )
                return
            except Exception as requeue_exc:  # pragma: no cover - runtime/network dependent
                logger.exception(
                    "Failed to re-queue message id=%s after error=%s requeue_error=%s",
                    message_id,
                    error,
                    requeue_exc,
                )
                return

        try:
            await self.redis.xadd(DLQ_STREAM_KEY, payload)
            await self.redis.xack(self.stream_key, self.group_name, message_id)
            logger.error(
                "Moved message to DLQ id=%s retries=%s error=%s",
                message_id,
                retry_count,
                error,
            )
        except Exception as dlq_exc:  # pragma: no cover - runtime/network dependent
            logger.exception(
                "Failed to move message to DLQ id=%s error=%s dlq_error=%s",
                message_id,
                error,
                dlq_exc,
            )


async def run_ingestor() -> None:
    """Run the Redis Streams ingestor worker until cancelled."""
    redis_client = await get_redis_client()
    ingestor = RedisStreamIngestor(
        redis_client=redis_client,
        stream_key=os.getenv("SENTINEL_INGEST_STREAM_KEY", STREAM_KEY),
        group_name=os.getenv("SENTINEL_INGEST_GROUP_NAME", GROUP_NAME),
        consumer_name=os.getenv("SENTINEL_INGEST_CONSUMER_NAME"),
        max_retries=int(os.getenv("SENTINEL_INGEST_MAX_RETRIES", "3")),
    )

    await ingestor.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await ingestor.stop()
        await close_db_clients()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_ingestor())

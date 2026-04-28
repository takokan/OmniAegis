from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from redis.exceptions import ResponseError

try:
    from decision_layer.shared import close_db_clients, get_redis_client
except ModuleNotFoundError:  # pragma: no cover
    from shared import close_db_clients, get_redis_client


logger = logging.getLogger(__name__)

DECISION_STREAM_KEY = "sentinel:decision:stream"
DECISION_GROUP_NAME = "sentinel:decision:group"
HITL_QUEUE_KEY = "sentinel:hitl:queue"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_payload(fields: dict[str, Any]) -> dict[str, Any] | None:
    payload_raw = fields.get("payload")
    if payload_raw is None:
        return None
    if isinstance(payload_raw, (bytes, bytearray)):
        payload_raw = payload_raw.decode("utf-8", errors="replace")
    if isinstance(payload_raw, str):
        try:
            parsed = json.loads(payload_raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    if isinstance(payload_raw, dict):
        return payload_raw
    return None


async def _ensure_consumer_group(redis_client: Any, stream_key: str, group_name: str) -> None:
    try:
        await redis_client.xgroup_create(name=stream_key, groupname=group_name, id="$", mkstream=True)
        logger.info("Created decision stream group stream=%s group=%s", stream_key, group_name)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _enqueue_hitl(redis_client: Any, *, analysis: dict[str, Any]) -> None:
    confidence = _safe_float(analysis.get("confidence"), 0.0)
    verdict = str(analysis.get("verdict") or "inconclusive")

    # Priority: higher confidence first for piracy matches; else inverse for uncertain items.
    if verdict == "match":
        priority = float(min(max(confidence, 0.0), 1.0))
    else:
        priority = float(1.0 - min(max(confidence, 0.0), 1.0))

    item = {
        "id": str(analysis.get("asset_id") or f"hitl-{uuid4().hex[:10]}"),
        "asset_id": str(analysis.get("asset_id") or "unknown"),
        "url": str(analysis.get("upstream_url") or analysis.get("url") or ""),
        "verdict": verdict,
        "confidence": confidence,
        "analysis": analysis,
        "queued_at": _now_iso(),
        "status": "pending",
        "reason": "PIRACY_MATCH" if verdict == "match" else "REVIEW_REQUIRED",
    }

    await redis_client.zadd(HITL_QUEUE_KEY, {json.dumps(item): priority})


async def run_decision_stream_consumer() -> None:
    redis_client = await get_redis_client()

    stream_key = os.getenv("SENTINEL_DECISION_STREAM_KEY", DECISION_STREAM_KEY)
    group_name = os.getenv("SENTINEL_DECISION_GROUP_NAME", DECISION_GROUP_NAME)
    consumer_name = os.getenv("SENTINEL_DECISION_CONSUMER_NAME", f"decision-consumer-{uuid4().hex[:8]}")

    await _ensure_consumer_group(redis_client, stream_key, group_name)

    logger.info("Decision consumer started stream=%s group=%s consumer=%s", stream_key, group_name, consumer_name)

    block_ms = int(os.getenv("SENTINEL_DECISION_BLOCK_MS", "5000"))
    read_count = int(os.getenv("SENTINEL_DECISION_READ_COUNT", "32"))

    while True:
        results = await redis_client.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams={stream_key: ">"},
            count=read_count,
            block=block_ms,
        )
        if not results:
            continue

        for _stream, entries in results:
            for message_id, fields in entries:
                start = time.perf_counter()
                try:
                    analysis = _parse_payload(fields)
                    if analysis is None:
                        await redis_client.xack(stream_key, group_name, message_id)
                        continue

                    # Only enqueue actionable items:
                    # - verdict=match (high confidence piracy)
                    # - verdict=inconclusive (needs review)
                    verdict = str(analysis.get("verdict") or "inconclusive")
                    if verdict in {"match", "inconclusive"}:
                        await _enqueue_hitl(redis_client, analysis=analysis)

                    await redis_client.xack(stream_key, group_name, message_id)
                    logger.info(
                        "Decision msg acked id=%s verdict=%s confidence=%.4f latency_ms=%.2f",
                        message_id,
                        verdict,
                        _safe_float(analysis.get("confidence"), 0.0),
                        (time.perf_counter() - start) * 1000.0,
                    )
                except Exception as exc:  # pragma: no cover
                    logger.exception("Decision consumer error id=%s error=%s", message_id, exc)
                    # Do not ACK on failure; message remains pending.
                    await asyncio.sleep(0.5)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run_decision_stream_consumer())
    finally:
        asyncio.run(close_db_clients())


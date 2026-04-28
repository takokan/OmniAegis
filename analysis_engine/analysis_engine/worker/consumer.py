from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from uuid import uuid4

from upstash_redis.asyncio import Redis

from ..core.config import Settings
from ..core.redis_client import ensure_consumer_group, xlen
from ..domain.schemas import AnalysisResult, IngestJob
from ..services.analysis_service import AnalysisInputs, AnalysisService
from ..services.metrics import piracy_detections_total, streams_scanned_total, worker_latency_seconds
from ..services.stream_probe import StreamProbeService
from ..services.waf_evasion import RotatingIdentityProvider


logger = logging.getLogger(__name__)


def _coerce_fields(fields: Any) -> dict[str, Any]:
    # Upstash returns fields as flat lists sometimes; normalize to dict[str, Any].
    if isinstance(fields, dict):
        return fields
    if isinstance(fields, list):
        out: dict[str, Any] = {}
        for i in range(0, len(fields) - 1, 2):
            out[str(fields[i])] = fields[i + 1]
        return out
    return {}


class AnalysisWorker:
    def __init__(
        self,
        *,
        redis: Redis,
        settings: Settings,
        probe: StreamProbeService,
        identity: RotatingIdentityProvider,
        analyzer: AnalysisService,
    ) -> None:
        self.redis = redis
        self.settings = settings
        self.probe = probe
        self.identity = identity
        self.analyzer = analyzer

        self.consumer_name = f"{settings.ingest_consumer_name}-{uuid4().hex[:8]}"
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

        self._buffer: asyncio.Queue[IngestJob] = asyncio.Queue(maxsize=settings.local_buffer_max)

    async def start(self) -> None:
        if self._task is not None:
            return
        await ensure_consumer_group(self.redis, stream_key=self.settings.ingest_stream_key, group_name=self.settings.ingest_group_name)
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="analysis-engine-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        producer = asyncio.create_task(self._produce_loop(), name="analysis-producer")
        consumers = [asyncio.create_task(self._consume_loop(i), name=f"analysis-consumer-{i}") for i in range(2)]
        try:
            await asyncio.gather(producer, *consumers)
        finally:
            for t in [producer, *consumers]:
                t.cancel()

    async def _produce_loop(self) -> None:
        while not self._stop.is_set():
            # Backpressure: if decision stream is too long, pause reading.
            if await xlen(self.redis, self.settings.decision_stream_key) > self.settings.decision_stream_backpressure_xlen:
                await asyncio.sleep(0.5)
                continue

            resp: Any = await self.redis.execute(
                "XREADGROUP",
                "GROUP",
                self.settings.ingest_group_name,
                self.consumer_name,
                "COUNT",
                "16",
                "BLOCK",
                "5000",
                "STREAMS",
                self.settings.ingest_stream_key,
                ">",
            )
            if not resp:
                continue

            # resp shape: [[stream, [[id, [k,v,k,v...]], ...]]]
            for _stream, entries in resp:
                for message_id, raw_fields in entries:
                    fields = _coerce_fields(raw_fields)
                    url = (fields.get("url") or fields.get("source_url") or fields.get("canonical_url") or fields.get("source") or "").strip()
                    asset_id = (fields.get("asset_id") or fields.get("content_digest") or url or f"asset:{message_id}").strip()
                    if not url:
                        await self._ack_and_publish_dropped(message_id, asset_id, url, error="missing url/source_url")
                        continue

                    job = IngestJob(message_id=str(message_id), url=url, asset_id=asset_id, metadata=fields)
                    try:
                        self._buffer.put_nowait(job)
                    except asyncio.QueueFull:
                        # Local buffer full -> drop quickly to avoid starvation.
                        await self._ack_and_publish_dropped(message_id, asset_id, url, error="local buffer full")

    async def _consume_loop(self, worker_idx: int) -> None:
        while not self._stop.is_set():
            job = await self._buffer.get()
            start = time.perf_counter()
            try:
                await self._handle_job(job)
            finally:
                worker_latency_seconds.observe(time.perf_counter() - start)
                self._buffer.task_done()

    async def _handle_job(self, job: IngestJob) -> None:
        streams_scanned_total.inc()
        identity = self.identity.choose()
        headers = {"User-Agent": identity.user_agent}

        try:
            probe = await self.probe.resolve_with_ytdlp(job.url, user_agent=identity.user_agent, proxy=identity.proxy)
        except TimeoutError as exc:
            await self._ack_and_publish_dropped(job.message_id, job.asset_id or "unknown", job.url, error=str(exc))
            return
        except Exception as exc:
            await self._ack_and_publish_dropped(job.message_id, job.asset_id or "unknown", job.url, error=f"probe failed: {exc}")
            return

        # If extractor indicates not live, drop quickly.
        if probe.is_live is False:
            await self._ack_and_publish_dropped(job.message_id, job.asset_id or "unknown", job.url, error="stream not live")
            return

        try:
            result = await self.analyzer.analyze(
                AnalysisInputs(
                    asset_id=job.asset_id or "unknown",
                    url=probe.playable_url,
                    headers=headers,
                )
            )
        except Exception as exc:
            await self._ack_and_publish_dropped(job.message_id, job.asset_id or "unknown", job.url, error=f"analysis failed: {exc}")
            return

        if result.verdict == "match":
            piracy_detections_total.inc()

        await self._publish_result(result, upstream_message_id=job.message_id, upstream_url=job.url)
        await self.redis.execute("XACK", self.settings.ingest_stream_key, self.settings.ingest_group_name, job.message_id)

    async def _publish_result(self, result: AnalysisResult, *, upstream_message_id: str, upstream_url: str) -> None:
        payload = result.model_dump()
        payload["upstream_message_id"] = upstream_message_id
        payload["upstream_url"] = upstream_url
        await self.redis.execute(
            "XADD",
            self.settings.decision_stream_key,
            "*",
            "payload",
            json.dumps(payload),
        )

    async def _ack_and_publish_dropped(self, message_id: str, asset_id: str, url: str, *, error: str) -> None:
        dropped = AnalysisResult(asset_id=asset_id, url=url or "", confidence=0.0, verdict="dropped", error=error)
        await self._publish_result(dropped, upstream_message_id=message_id, upstream_url=url)
        await self.redis.execute("XACK", self.settings.ingest_stream_key, self.settings.ingest_group_name, message_id)


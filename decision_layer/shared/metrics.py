from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

from .config import Settings, get_settings


logger = logging.getLogger(__name__)


@dataclass
class SentinelMetrics:
    """Service-local Prometheus metrics bundle.

    Each service should instantiate its own `CollectorRegistry` to avoid cross-service
    collisions when multiple workers/processes run concurrently.
    """

    service_name: str
    registry: CollectorRegistry
    assets_ingested_total: Any
    decisions_total: Any
    hitl_queue_depth: Any

    def inc_assets_ingested(self, value: float = 1.0) -> None:
        self.assets_ingested_total.inc(value)

    def inc_decisions(self, value: float = 1.0) -> None:
        self.decisions_total.inc(value)

    def set_hitl_queue_depth(self, value: float) -> None:
        self.hitl_queue_depth.set(float(value))


def create_sentinel_metrics(service_name: str) -> SentinelMetrics:
    """Create a service-isolated metrics registry and standard Sentinel metrics."""

    registry = CollectorRegistry(auto_describe=True)

    assets_ingested_total = Counter(
        "sentinel_assets_ingested_total",
        "Total number of assets ingested by Sentinel services.",
        registry=registry,
        labelnames=("service",),
    )
    decisions_total = Counter(
        "sentinel_decisions_total",
        "Total number of policy/inference decisions produced.",
        registry=registry,
        labelnames=("service",),
    )
    hitl_queue_depth = Gauge(
        "sentinel_hitl_queue_depth",
        "Current number of queued HITL review items.",
        registry=registry,
        labelnames=("service",),
    )

    return SentinelMetrics(
        service_name=service_name,
        registry=registry,
        assets_ingested_total=assets_ingested_total.labels(service=service_name),
        decisions_total=decisions_total.labels(service=service_name),
        hitl_queue_depth=hitl_queue_depth.labels(service=service_name),
    )


class GrafanaMetricsPusher:
    """Push metrics to Grafana Cloud on a fixed interval.

    This uses an authenticated HTTP push endpoint configured via
    `GRAFANA_PROMETHEUS_URL` and `GRAFANA_API_KEY`.
    """

    def __init__(
        self,
        metrics: SentinelMetrics,
        settings: Settings | None = None,
        push_interval_seconds: float = 15.0,
        timeout_seconds: float = 8.0,
        instance: str = "local-python",
    ) -> None:
        self.metrics = metrics
        self.settings = settings or get_settings()
        self.push_interval_seconds = push_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.instance = instance

        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def _build_headers(self) -> dict[str, str]:
        api_key = self.settings.grafana_api_key.get_secret_value()
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "text/plain; version=0.0.4",
        }

    def _build_push_url(self) -> str:
        # Accept either a full push endpoint or a base URL.
        base_url = str(self.settings.grafana_prometheus_url).rstrip("/")
        if base_url.endswith("/api/prom/push"):
            return base_url
        return f"{base_url}/api/prom/push"

    async def push_once(self) -> None:
        url = self._build_push_url()
        body = generate_latest(self.metrics.registry)
        params = {
            "job": self.metrics.service_name,
            "instance": self.instance,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                url,
                content=body,
                headers=self._build_headers(),
                params=params,
            )
            response.raise_for_status()

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.push_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - network/runtime dependent
                logger.exception(
                    "Grafana metrics push failed service=%s error=%s",
                    self.metrics.service_name,
                    exc,
                )

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.push_interval_seconds)
            except TimeoutError:
                continue

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run_loop(),
            name=f"grafana-metrics-pusher-{self.metrics.service_name}",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


async def start_metrics_pusher(
    service_name: str,
    *,
    settings: Settings | None = None,
    push_interval_seconds: float = 15.0,
    instance: str = "local-python",
) -> tuple[SentinelMetrics, GrafanaMetricsPusher]:
    """Convenience bootstrap for service-local metrics and push loop."""

    metrics = create_sentinel_metrics(service_name=service_name)
    pusher = GrafanaMetricsPusher(
        metrics=metrics,
        settings=settings,
        push_interval_seconds=push_interval_seconds,
        instance=instance,
    )
    await pusher.start()
    return metrics, pusher

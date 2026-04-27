from __future__ import annotations

import time
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class MetricsRegistry:
    def __init__(self) -> None:
        self.model_version_gauge = Gauge("model_version_gauge", "Current model version")
        self.infringement_ece_gauge = Gauge("infringement_ece_gauge", "ECE of calibrated infringement model")
        self.inference_latency_seconds = Histogram(
            "inference_latency_seconds",
            "End-to-end request latency",
            labelnames=("path", "method", "status"),
            buckets=(0.01, 0.03, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
        )
        self.request_count = Counter(
            "pipeline_requests_total",
            "Total requests served",
            labelnames=("path", "method", "status"),
        )

    def set_model_version(self, version: float) -> None:
        self.model_version_gauge.set(version)

    def set_ece(self, ece: float) -> None:
        self.infringement_ece_gauge.set(float(ece))


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, metrics: MetricsRegistry) -> None:
        super().__init__(app)
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status = "500"
        path = request.url.path
        method = request.method
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            elapsed = time.perf_counter() - start
            self.metrics.inference_latency_seconds.labels(path=path, method=method, status=status).observe(elapsed)
            self.metrics.request_count.labels(path=path, method=method, status=status).inc()


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

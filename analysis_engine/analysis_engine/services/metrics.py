from __future__ import annotations

from prometheus_client import Counter, Histogram


streams_scanned_total = Counter("analysis_streams_scanned_total", "Total number of streams/jobs scanned")
piracy_detections_total = Counter("analysis_piracy_detections_total", "Total number of piracy detections (verdict=match)")
false_positives_total = Counter("analysis_false_positives_total", "Total false positives (requires downstream feedback)")

worker_latency_seconds = Histogram(
    "analysis_worker_latency_seconds",
    "End-to-end worker latency per job",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)


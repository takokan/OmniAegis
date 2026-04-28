from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str

    ingest_stream_key: str = "sentinel:ingest:stream"
    ingest_group_name: str = "sentinel:analysis:group"
    ingest_consumer_name: str = "analysis-engine"

    decision_stream_key: str = "sentinel:decision:stream"

    readiness_timeout_seconds: float = 10.0
    decision_stream_backpressure_xlen: int = 2000
    local_buffer_max: int = 256

    user_agent_pool: list[str] = None  # type: ignore[assignment]
    proxy_pool: list[str] = None  # type: ignore[assignment]

    yolo_enabled: bool = True
    yolo_model: str = "yolov8n.pt"

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    frame_sample_seconds: float = 2.0
    frame_fps: int = 1

    confidence_threshold: float = 0.85


def load_settings() -> Settings:
    rest_url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
    rest_token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not rest_url or not rest_token:
        raise RuntimeError("Missing UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN in environment")

    return Settings(
        upstash_redis_rest_url=rest_url,
        upstash_redis_rest_token=rest_token,
        ingest_stream_key=os.getenv("SENTINEL_INGEST_STREAM_KEY", "sentinel:ingest:stream"),
        ingest_group_name=os.getenv("SENTINEL_ANALYSIS_GROUP_NAME", "sentinel:analysis:group"),
        ingest_consumer_name=os.getenv("SENTINEL_ANALYSIS_CONSUMER_NAME", "analysis-engine"),
        decision_stream_key=os.getenv("SENTINEL_DECISION_STREAM_KEY", "sentinel:decision:stream"),
        readiness_timeout_seconds=float(os.getenv("STREAM_READINESS_TIMEOUT_SECONDS", "10")),
        decision_stream_backpressure_xlen=int(os.getenv("DECISION_STREAM_BACKPRESSURE_XLEN", "2000")),
        local_buffer_max=int(os.getenv("ANALYSIS_LOCAL_BUFFER_MAX", "256")),
        user_agent_pool=_csv(os.getenv("USER_AGENT_POOL")) or _csv(os.getenv("SCRAPER_USER_AGENT_POOL")),
        proxy_pool=_csv(os.getenv("PROXY_POOL")) or _csv(os.getenv("SCRAPER_PROXY_POOL")),
        yolo_enabled=str(os.getenv("ANALYSIS_YOLO_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"},
        yolo_model=os.getenv("ANALYSIS_YOLO_MODEL", "yolov8n.pt"),
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
        ffprobe_path=os.getenv("FFPROBE_PATH", "ffprobe"),
        frame_sample_seconds=float(os.getenv("ANALYSIS_FRAME_SAMPLE_SECONDS", "2")),
        frame_fps=int(os.getenv("ANALYSIS_FRAME_FPS", "1")),
        confidence_threshold=float(os.getenv("ANALYSIS_CONFIDENCE_THRESHOLD", "0.85")),
    )


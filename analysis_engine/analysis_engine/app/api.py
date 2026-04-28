from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..core.config import load_settings
from ..core.redis_client import get_redis
from ..services.analysis_service import AnalysisService
from ..services.fingerprint import FingerprintService
from ..services.frame_sampler import FFmpegFrameSampler
from ..services.logo_detector import LogoDetector
from ..services.stream_probe import StreamProbeService
from ..services.waf_evasion import RotatingIdentityProvider
from ..worker.consumer import AnalysisWorker


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    redis = get_redis(settings)

    identity = RotatingIdentityProvider(settings.user_agent_pool, settings.proxy_pool)
    probe = StreamProbeService(readiness_timeout_seconds=settings.readiness_timeout_seconds)
    sampler = FFmpegFrameSampler(ffmpeg_path=settings.ffmpeg_path)
    fingerprint = FingerprintService(truth_db={})  # TODO: wire to SoT store
    detector = LogoDetector(enabled=settings.yolo_enabled, model_name=settings.yolo_model)

    analyzer = AnalysisService(
        sampler=sampler,
        fingerprint=fingerprint,
        logo_detector=detector,
        frame_sample_seconds=settings.frame_sample_seconds,
        frame_fps=settings.frame_fps,
        confidence_threshold=settings.confidence_threshold,
    )

    worker = AnalysisWorker(redis=redis, settings=settings, probe=probe, identity=identity, analyzer=analyzer)

    app.state.settings = settings
    app.state.redis = redis
    app.state.worker = worker

    await worker.start()
    try:
        yield
    finally:
        await worker.stop()
        try:
            # Upstash client doesn't require explicit close, but keep this safe.
            await asyncio.sleep(0)
        except Exception:
            pass


app = FastAPI(title="OmniAegis Analysis Engine", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ANALYSIS_ENGINE_PORT", "8090")))


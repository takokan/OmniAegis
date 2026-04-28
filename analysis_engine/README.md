## OmniAegis Analysis Engine

This service is the "Eyes" of OmniAegis.

### Responsibilities
- Consume URLs/jobs from Upstash Redis Stream `sentinel:ingest:stream`
- Perform **fast stream readiness probing** (abort if not live within 10s)
- Sample a small window of frames using `ffmpeg` (no full download)
- Run modular multimodal checks:
  - **Logo/overlay detection** (YOLOv8 if available)
  - **Perceptual hashing** (pHash) over sampled frames
- Publish `AnalysisResult` objects to Upstash Redis Stream `sentinel:decision:stream`
- Expose Prometheus metrics at `GET /metrics`

### Environment
This service uses Upstash Redis via REST (recommended for managed cloud):
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`

Optional:
- `SENTINEL_INGEST_STREAM_KEY` (default `sentinel:ingest:stream`)
- `SENTINEL_DECISION_STREAM_KEY` (default `sentinel:decision:stream`)
- `STREAM_READINESS_TIMEOUT_SECONDS` (default `10`)
- `DECISION_STREAM_BACKPRESSURE_XLEN` (default `2000`)
- `PROXY_POOL` (comma-separated, optional)
- `USER_AGENT_POOL` (comma-separated, optional)

### Run locally (non-container)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m analysis_engine.app.api
```

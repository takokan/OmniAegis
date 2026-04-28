from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any
from uuid import uuid4

from redis.exceptions import ResponseError

try:
    from decision_layer.shared import close_db_clients, get_redis_client
    from decision_layer.services.web_scraper.main import run_web_scraper
except ModuleNotFoundError:  # pragma: no cover
    from shared import close_db_clients, get_redis_client
    from services.web_scraper.main import run_web_scraper


logger = logging.getLogger(__name__)

JOB_STREAM_KEY = "sentinel:search:jobs"
JOB_GROUP_NAME = "sentinel:search:group"


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _loads_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if str(v).strip()]
        except Exception:
            return [value] if value.strip() else []
    return []


def _coerce_fields(fields: Any) -> dict[str, Any]:
    if isinstance(fields, dict):
        return fields
    if isinstance(fields, list):
        out: dict[str, Any] = {}
        for i in range(0, len(fields) - 1, 2):
            out[str(fields[i])] = fields[i + 1]
        return out
    return {}


def _normalize_terms(terms: list[str]) -> list[str]:
    cleaned: list[str] = []
    for t in terms:
        value = re.sub(r"\s+", " ", str(t or "").strip())
        if len(value) < 3:
            continue
        cleaned.append(value.lower())
    # stable unique
    out: list[str] = []
    seen: set[str] = set()
    for t in cleaned:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:50]


async def _ensure_group(redis_client: Any, stream_key: str, group_name: str) -> None:
    try:
        await redis_client.xgroup_create(name=stream_key, groupname=group_name, id="$", mkstream=True)
        logger.info("Created search job stream group stream=%s group=%s", stream_key, group_name)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def run_search_orchestrator() -> None:
    redis_client = await get_redis_client()

    stream_key = os.getenv("SENTINEL_SEARCH_JOB_STREAM_KEY", JOB_STREAM_KEY)
    group_name = os.getenv("SENTINEL_SEARCH_JOB_GROUP_NAME", JOB_GROUP_NAME)
    consumer_name = os.getenv("SENTINEL_SEARCH_JOB_CONSUMER_NAME", f"search-orchestrator-{uuid4().hex[:8]}")

    await _ensure_group(redis_client, stream_key, group_name)

    # Default crawl seeds for “instant” search. For production, point these at
    # your owned discovery pages / curated aggregators.
    default_seeds = _csv(os.getenv("SEARCH_SEED_URLS")) or [
        "https://www.reddit.com/",
        "https://www.youtube.com/",
        "https://www.twitch.tv/",
    ]
    allow_domains = _csv(os.getenv("SEARCH_ALLOW_DOMAINS"))
    blocked_domains = _csv(os.getenv("SEARCH_BLOCKED_DOMAINS"))

    logger.info("Search orchestrator started stream=%s group=%s consumer=%s", stream_key, group_name, consumer_name)

    while True:
        results = await redis_client.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams={stream_key: ">"},
            count=int(os.getenv("SEARCH_JOB_READ_COUNT", "4")),
            block=int(os.getenv("SEARCH_JOB_BLOCK_MS", "5000")),
        )
        if not results:
            continue

        for _stream, entries in results:
            for message_id, raw_fields in entries:
                fields = _coerce_fields(raw_fields)
                asset_id = str(fields.get("asset_id") or "").strip()
                protected_terms = _normalize_terms(_loads_json_list(fields.get("protected_terms")))

                if not asset_id or not protected_terms:
                    await redis_client.xack(stream_key, group_name, message_id)
                    continue

                try:
                    await run_web_scraper(
                        seed_urls=default_seeds,
                        allow_domains=allow_domains or None,
                        blocked_domains=blocked_domains or None,
                        protected_terms=protected_terms,
                        max_depth=int(os.getenv("SEARCH_MAX_DEPTH", "1")),
                        max_pages=int(os.getenv("SEARCH_MAX_PAGES", "80")),
                        require_allowlist=str(os.getenv("SEARCH_REQUIRE_ALLOWLIST", "0")).strip().lower() in {"1", "true", "yes", "on"},
                        min_emit_score=float(os.getenv("SEARCH_MIN_EMIT_SCORE", "0.55")),
                        redis_stream=os.getenv("SENTINEL_INGEST_STREAM_KEY", "sentinel:ingest:stream"),
                        tier=os.getenv("SEARCH_DEFAULT_TIER", "tier_1"),
                        priority=float(os.getenv("SEARCH_DEFAULT_PRIORITY", "0.85")),
                    )
                    await redis_client.xack(stream_key, group_name, message_id)
                    logger.info("Search job completed asset_id=%s terms=%s", asset_id, len(protected_terms))
                except Exception as exc:  # pragma: no cover
                    logger.exception("Search job failed asset_id=%s error=%s", asset_id, exc)
                    # Do not ACK so it can be retried.
                    await asyncio.sleep(0.5)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run_search_orchestrator())
    finally:
        asyncio.run(close_db_clients())


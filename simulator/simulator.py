#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import signal
import string
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError


DECISION_STREAM_KEY = "sentinel:decision:stream"
HITL_QUEUE_KEY = "sentinel:hitl:queue"
BLOCKCHAIN_AUDIT_STREAM_KEY = "sentinel:blockchain:audit:stream"

MEDIA_TYPES = ("image", "video", "audio", "text")
VERDICTS = ("match", "inconclusive", "no_match")


@dataclass
class SimUser:
    user_id: str
    email: str
    org_id: str
    role: str = "creator"
    signed_in: bool = True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def random_hash_hex(length: int = 64) -> str:
    return "0x" + "".join(random.choices("0123456789abcdef", k=length))


def random_url(modality: str, user_id: str) -> str:
    ext = {"image": "png", "video": "mp4", "audio": "wav", "text": "txt"}[modality]
    slug = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"https://synthetic.omniaegis.local/{user_id}/{modality}/{slug}.{ext}"


def _load_env_file() -> None:
    """Best-effort .env loader for local runs without python-dotenv."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = raw_value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


def _build_upstash_redis_url() -> str | None:
    """Construct a Redis TLS URL from Upstash REST credentials when available."""
    rest_url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
    token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not rest_url or not token:
        return None

    parsed = urlparse(rest_url)
    host = parsed.netloc
    if not host:
        return None
    return f"rediss://default:{token}@{host}:6379"


def _resolve_redis_url(cli_redis_url: str | None) -> str:
    _load_env_file()

    if cli_redis_url:
        return cli_redis_url

    sim_redis_url = (os.getenv("SIM_REDIS_URL") or "").strip()
    if sim_redis_url:
        return sim_redis_url

    redis_url = (os.getenv("REDIS_URL") or "").strip()
    upstash_redis_url = _build_upstash_redis_url()

    if redis_url:
        parsed = urlparse(redis_url)
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} and upstash_redis_url:
            return upstash_redis_url
        return redis_url

    if upstash_redis_url:
        return upstash_redis_url

    return "redis://127.0.0.1:6379/0"


def make_analysis_payload(user: SimUser, idx: int) -> dict[str, Any]:
    modality = random.choice(MEDIA_TYPES)
    verdict = random.choices(VERDICTS, weights=(0.35, 0.5, 0.15), k=1)[0]
    confidence = round(random.uniform(0.45, 0.99), 4)
    asset_id = f"asset-{user.user_id}-{idx}-{uuid4().hex[:8]}"
    decision_id = f"decision-{uuid4().hex}"
    return {
        "decision_id": decision_id,
        "asset_id": asset_id,
        "uploader_id": user.user_id,
        "uploader_email": user.email,
        "org_id": user.org_id,
        "modality": modality,
        "upstream_url": random_url(modality, user.user_id),
        "verdict": verdict,
        "confidence": confidence,
        "policy_id": random.randint(1, 12),
        "risk_score_bps": int(confidence * 10000),
        "high_stakes": bool(random.random() > 0.65),
        "model_version": "sim-v1",
        "trace_id": uuid4().hex,
        "created_at": now_iso(),
    }


def hitl_priority(analysis: dict[str, Any]) -> float:
    confidence = float(analysis.get("confidence", 0.0))
    verdict = str(analysis.get("verdict", "inconclusive"))
    if verdict == "match":
        return max(0.0, min(confidence, 1.0))
    return 1.0 - max(0.0, min(confidence, 1.0))


async def emit_blockchain_log(redis_client: Redis, analysis: dict[str, Any], action: str) -> None:
    details = {
        "asset_id": analysis["asset_id"],
        "decision_id": analysis["decision_id"],
        "verdict": analysis["verdict"],
        "confidence": analysis["confidence"],
        "modality": analysis["modality"],
        "trace_id": analysis["trace_id"],
    }
    payload = {
        "id": f"AUD-{uuid4().hex[:12]}",
        "action": action,
        "timestamp": now_iso(),
        "policyVersion": analysis.get("model_version", "sim-v1"),
        "reasoningHash": random_hash_hex(),
        "admin": analysis["uploader_email"],
        "details": json.dumps(details, ensure_ascii=True),
    }
    await redis_client.xadd(BLOCKCHAIN_AUDIT_STREAM_KEY, payload)


async def emit_decision(redis_client: Redis, analysis: dict[str, Any], fallback_hitl: bool) -> None:
    await redis_client.xadd(DECISION_STREAM_KEY, {"payload": json.dumps(analysis, ensure_ascii=True)})

    if fallback_hitl:
        item = {
            "id": analysis["asset_id"],
            "asset_id": analysis["asset_id"],
            "url": analysis.get("upstream_url", ""),
            "verdict": analysis["verdict"],
            "confidence": float(analysis["confidence"]),
            "analysis": analysis,
            "queued_at": now_iso(),
            "status": "pending",
            "reason": "PIRACY_MATCH" if analysis["verdict"] == "match" else "REVIEW_REQUIRED",
        }
        await redis_client.zadd(HITL_QUEUE_KEY, {json.dumps(item): hitl_priority(analysis)})


def build_users(count: int) -> list[SimUser]:
    return [
        SimUser(
            user_id=f"user-{idx+1:03d}",
            email=f"user{idx+1:03d}@omniaegis.sim",
            org_id=f"org-{(idx % 5) + 1:02d}",
        )
        for idx in range(count)
    ]


async def simulate_user(
    redis_client: Redis,
    user: SimUser,
    *,
    iterations: int,
    min_delay: float,
    max_delay: float,
    fallback_hitl: bool,
) -> None:
    await emit_blockchain_log(
        redis_client,
        {
            "asset_id": "auth-session",
            "decision_id": uuid4().hex,
            "verdict": "session_open",
            "confidence": 1.0,
            "modality": "auth",
            "trace_id": uuid4().hex,
            "model_version": "sim-v1",
            "uploader_email": user.email,
        },
        action="USER_SIGNED_IN",
    )
    for idx in range(iterations):
        analysis = make_analysis_payload(user, idx)
        await emit_decision(redis_client, analysis, fallback_hitl=fallback_hitl)
        await emit_blockchain_log(redis_client, analysis, action="CONTENT_ANALYZED")
        if analysis["verdict"] in {"match", "inconclusive"}:
            await emit_blockchain_log(redis_client, analysis, action="HITL_ENQUEUED")
        await asyncio.sleep(random.uniform(min_delay, max_delay))


async def run_simulation(args: argparse.Namespace) -> None:
    redis_url = _resolve_redis_url(args.redis_url)
    redis_client = Redis.from_url(redis_url, decode_responses=True)
    users = build_users(args.users)

    stop_event = asyncio.Event()

    def _stop_handler(*_: Any) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop_handler)

    try:
        try:
            await redis_client.ping()
        except RedisConnectionError as exc:
            raise RuntimeError(
                "Redis connection failed. Set --redis-url or SIM_REDIS_URL to a reachable Redis instance. "
                "Tip: if .env includes UPSTASH_REDIS_REST_URL/TOKEN, the simulator can auto-derive a rediss URL."
            ) from exc

        round_idx = 0
        while not stop_event.is_set():
            round_idx += 1
            print(f"[sim] round={round_idx} users={len(users)} iterations={args.iterations}")
            tasks = [
                asyncio.create_task(
                    simulate_user(
                        redis_client,
                        user,
                        iterations=args.iterations,
                        min_delay=args.min_delay,
                        max_delay=args.max_delay,
                        fallback_hitl=args.fallback_hitl,
                    )
                )
                for user in users
            ]
            await asyncio.gather(*tasks)
            if not args.continuous:
                break
            await asyncio.sleep(args.pause_between_rounds)
    finally:
        await redis_client.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OmniAegis multi-user simulator for HITL and blockchain audit streams."
    )
    parser.add_argument("--users", type=int, default=8, help="number of synthetic signed-in users")
    parser.add_argument("--iterations", type=int, default=5, help="uploads generated per user per round")
    parser.add_argument("--min-delay", type=float, default=0.15, help="min delay between user uploads")
    parser.add_argument("--max-delay", type=float, default=1.2, help="max delay between user uploads")
    parser.add_argument("--continuous", action="store_true", help="run indefinitely")
    parser.add_argument("--pause-between-rounds", type=float, default=2.0, help="pause between rounds when continuous")
    parser.add_argument("--fallback-hitl", action="store_true", help="directly push HITL queue items if consumer is disabled")
    parser.add_argument("--redis-url", type=str, default=None, help="override Redis URL")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_simulation(parse_args()))

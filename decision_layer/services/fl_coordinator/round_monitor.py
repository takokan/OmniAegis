from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import redis  # type: ignore[reportMissingImports]
from prometheus_client import Counter, Gauge

try:
    from shared.training_buffer import RedisBufferConfig, TrainingBuffer
except ModuleNotFoundError:  # pragma: no cover
    from decision_layer.shared.training_buffer import RedisBufferConfig, TrainingBuffer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoundMonitorConfig:
    """Runtime config for FL round orchestration lifecycle."""

    redis_url: str = "redis://localhost:6379/0"
    threshold: int = 50
    round_samples_key_prefix: str = "fl:round:samples"
    trigger_channel: str = "trigger_fl"
    model_ready_channel: str = "fl:global_model_ready"
    model_pointer_key: str = "model_registry:production_pointer"
    model_candidate_prefix: str = "model_registry:candidate"
    max_retries: int = 3
    poll_interval_seconds: float = 1.0


class RoundMonitor:
    """Redis lifecycle orchestrator for trigger->round->promotion flow.

    Responsibilities:
    - Monitor the HITL buffer and trigger FL rounds once sample threshold is met.
    - Handle explicit trigger messages (`trigger_fl`) safely via pub/sub.
    - Persist round payloads to Redis atomically for edge simulation consumption.
    - Apply retry and rollback guards for failed rounds.
    - Promote candidate models only when validation metrics do not regress.
    """

    def __init__(
        self,
        config: RoundMonitorConfig | None = None,
        on_round_start: Callable[[str, list[dict[str, Any]]], None] | None = None,
    ) -> None:
        env_config = RoundMonitorConfig(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            threshold=int(os.getenv("FL_ROUND_THRESHOLD", "50")),
            round_samples_key_prefix=os.getenv("FL_ROUND_SAMPLES_KEY_PREFIX", "fl:round:samples"),
            trigger_channel=os.getenv("FL_TRIGGER_CHANNEL", "trigger_fl"),
            model_ready_channel=os.getenv("FL_MODEL_READY_CHANNEL", "fl:global_model_ready"),
            model_pointer_key=os.getenv("FL_MODEL_POINTER_KEY", "model_registry:production_pointer"),
            model_candidate_prefix=os.getenv("FL_MODEL_CANDIDATE_PREFIX", "model_registry:candidate"),
            max_retries=int(os.getenv("FL_ROUND_MAX_RETRIES", "3")),
            poll_interval_seconds=float(os.getenv("FL_MONITOR_POLL_SECONDS", "1.0")),
        )
        self.config = config or env_config
        self.redis = redis.Redis.from_url(self.config.redis_url, decode_responses=True)
        self.buffer = TrainingBuffer(
            RedisBufferConfig(
                redis_url=self.config.redis_url,
                list_key=os.getenv("HITL_BUFFER_KEY", "hitl:training_buffer"),
                trigger_channel=self.config.trigger_channel,
            )
        )
        self.on_round_start = on_round_start

        self.round_failures = Counter("fl_round_failures_total", "Failed FL round attempts")
        self.round_started = Counter("fl_round_started_total", "Started FL rounds")
        self.round_retries = Counter("fl_round_retries_total", "Retried FL round attempts")
        self.privacy_budget_remaining = Gauge(
            "privacy_budget_remaining",
            "Remaining privacy budget fraction aggregated across active clients",
        )

    def _persist_round_samples(self, round_id: str, samples: list[dict[str, Any]]) -> str:
        key = f"{self.config.round_samples_key_prefix}:{round_id}"
        payload = json.dumps(samples, separators=(",", ":"))
        self.redis.set(key, payload, ex=3600)
        self.redis.set("fl:active_round_id", round_id, ex=3600)
        return key

    def _restore_samples(self, samples: list[dict[str, Any]]) -> None:
        for sample in samples:
            self.buffer.push_sample(sample)

    def _attempt_round(self, samples: list[dict[str, Any]], reason: str) -> bool:
        round_id = str(uuid.uuid4())
        self.round_started.inc()
        self._persist_round_samples(round_id, samples)

        logger.info("Starting FL round %s due to %s with %d samples", round_id, reason, len(samples))
        if self.on_round_start is None:
            self.buffer.publish_trigger({"event": "start_round", "round_id": round_id, "sample_count": len(samples)})
            return True

        try:
            self.on_round_start(round_id, samples)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Round start callback failed for round %s: %s", round_id, exc)
            return False

    def _trigger_round_with_retry(self, samples: list[dict[str, Any]], reason: str) -> None:
        if not samples:
            return

        for attempt in range(1, self.config.max_retries + 1):
            ok = self._attempt_round(samples, reason=reason)
            if ok:
                return

            self.round_retries.inc()
            backoff = 0.5 * (2 ** (attempt - 1))
            logger.warning("Retrying FL round in %.2fs (attempt %d/%d)", backoff, attempt, self.config.max_retries)
            time.sleep(backoff)

        self.round_failures.inc()
        self._restore_samples(samples)
        raise RuntimeError("FL round failed after max retries; samples restored to HITL buffer")

    def _poll_privacy_budget(self, target_epsilon: float = 1.0) -> None:
        keys = self.redis.keys("fl:node:*:epsilon")
        if not keys:
            self.privacy_budget_remaining.set(1.0)
            return

        epsilons: list[float] = []
        for key in keys:
            value = self.redis.get(key)
            if value is None:
                continue
            try:
                epsilons.append(float(value))
            except ValueError:
                continue

        if not epsilons:
            self.privacy_budget_remaining.set(1.0)
            return

        avg_epsilon = sum(epsilons) / float(len(epsilons))
        remaining = max(0.0, 1.0 - (avg_epsilon / max(target_epsilon, 1e-12)))
        self.privacy_budget_remaining.set(remaining)

    def _handle_model_ready(self, raw_message: str) -> None:
        """Rollback guard for model registry promotion.

        Expected payload schema:
        {
          "candidate_id": "round-uuid",
          "metrics": {"accuracy": 0.94, "ece": 0.06},
          "weights_key": "model_registry:candidate:<id>"
        }
        """
        payload = json.loads(raw_message)
        candidate_id = str(payload.get("candidate_id", ""))
        metrics = dict(payload.get("metrics", {}))
        accuracy = float(metrics.get("accuracy", 0.0))
        ece = float(metrics.get("ece", 1.0))
        weights_key = str(payload.get("weights_key") or f"{self.config.model_candidate_prefix}:{candidate_id}")

        if not candidate_id:
            raise ValueError("Missing candidate_id in model-ready payload")

        prod_pointer_raw = self.redis.get(self.config.model_pointer_key)
        previous_key = str(prod_pointer_raw) if prod_pointer_raw else ""
        previous_meta_key = f"{previous_key}:meta" if previous_key else ""

        prev_accuracy = 0.0
        prev_ece = 1.0
        if previous_meta_key:
            prev_meta_raw = self.redis.get(previous_meta_key)
            if prev_meta_raw:
                prev_meta = json.loads(prev_meta_raw)
                prev_accuracy = float(prev_meta.get("accuracy", 0.0))
                prev_ece = float(prev_meta.get("ece", 1.0))

        quality_regressed = (accuracy < prev_accuracy) or (ece > prev_ece)
        meta_payload = json.dumps({"accuracy": accuracy, "ece": ece}, separators=(",", ":"))
        self.redis.set(f"{weights_key}:meta", meta_payload, ex=7 * 24 * 3600)

        if quality_regressed:
            logger.warning(
                "Rollback guard rejected candidate %s (acc %.4f<%.4f or ece %.4f>%.4f)",
                candidate_id,
                accuracy,
                prev_accuracy,
                ece,
                prev_ece,
            )
            if previous_key:
                self.redis.set(self.config.model_pointer_key, previous_key)
            return

        self.redis.set(self.config.model_pointer_key, weights_key)
        logger.info("Promoted candidate model %s to production pointer", candidate_id)

    def run_forever(self) -> None:
        """Run monitor loop until process termination."""
        subscriber = self.buffer.create_subscriber()
        model_sub = self.redis.pubsub(ignore_subscribe_messages=True)
        model_sub.subscribe(self.config.model_ready_channel)

        try:
            while True:
                queued = self.buffer.length()
                if queued >= self.config.threshold:
                    samples = self.buffer.get_and_clear()
                    self._trigger_round_with_retry(samples=samples, reason="threshold")

                trigger_event = subscriber.get_message(timeout=0.1)
                if trigger_event and trigger_event.get("type") == "message":
                    samples = self.buffer.get_and_clear()
                    self._trigger_round_with_retry(samples=samples, reason="pubsub-trigger")

                model_event = model_sub.get_message(timeout=0.1)
                if model_event and model_event.get("type") == "message":
                    try:
                        self._handle_model_ready(str(model_event.get("data", "{}")))
                    except Exception as exc:
                        logger.exception("Model promotion listener failed: %s", exc)

                self._poll_privacy_budget(target_epsilon=1.0)
                time.sleep(self.config.poll_interval_seconds)
        finally:
            subscriber.close()
            model_sub.close()
            self.buffer.close()
            self.redis.close()

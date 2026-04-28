from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

import numpy as np
import redis  # type: ignore[reportMissingImports]

from .state_space import SentinelState


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        shadow_event = getattr(record, "shadow_event", None)
        if shadow_event is not None:
            payload["shadow_event"] = shadow_event

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(",", ":"), default=_json_default)


class ShadowPolicy(Protocol):
    def __call__(self, state: SentinelState, data: Mapping[str, Any]) -> Any: ...


@dataclass(frozen=True)
class ShadowModeConfig:
    """Runtime configuration for Sentinel shadow-mode comparison logging."""

    redis_url: str = "redis://localhost:6379/0"
    log_key: str = "sentinel:shadow:comparisons"
    max_entries: int = 100_000
    rl_timeout_ms: int = 50
    action_utilities: tuple[float, float, float] = (1.5, 0.8, 3.0)
    logger_name: str = "sentinel.shadow"


@dataclass(frozen=True)
class ShadowRecord:
    """Serialized comparison record persisted for auditing and metrics."""

    asset_id: str
    baseline_action: int
    rl_action: int | None
    confidence: float
    status: str
    state_vector: tuple[float, ...]
    baseline_result: Any = field(repr=False, compare=False, default=None)
    rl_result: Any = field(repr=False, compare=False, default=None)
    latency_ms: float = 0.0
    projected_reward: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class ShadowMetrics:
    """Aggregated shadow-mode metrics computed from persisted logs."""

    agreement_rate: float
    projected_reward: float
    sample_count: int
    comparable_count: int

    @classmethod
    def from_records(
        cls,
        records: Sequence[Mapping[str, Any]],
        action_utilities: tuple[float, float, float] = (1.5, 0.8, 3.0),
    ) -> ShadowMetrics:
        comparable = 0
        agreements = 0
        reward_total = 0.0

        for record in records:
            baseline_action = _coerce_action(record.get("baseline_action"))
            rl_action = _coerce_action(record.get("rl_action"))
            if baseline_action is None or rl_action is None:
                continue

            comparable += 1
            if baseline_action == rl_action:
                agreements += 1

            reward_total += _projected_reward(
                baseline_action=baseline_action,
                rl_action=rl_action,
                confidence=_coerce_float(record.get("confidence"), default=1.0),
                action_utilities=action_utilities,
            )

        agreement_rate = float(agreements / comparable) if comparable > 0 else 0.0
        projected_reward = float(reward_total / comparable) if comparable > 0 else 0.0
        return cls(
            agreement_rate=agreement_rate,
            projected_reward=projected_reward,
            sample_count=len(records),
            comparable_count=comparable,
        )

    @classmethod
    def from_logger(cls, logger: ShadowLogger, limit: int | None = None) -> ShadowMetrics:
        records = logger.fetch_recent(limit=limit)
        return cls.from_records(records, action_utilities=logger.config.action_utilities)


class ShadowLogger:
    """Thread-safe JSON logger that persists shadow comparisons in Redis."""

    def __init__(self, config: ShadowModeConfig | None = None) -> None:
        self.config = config or ShadowModeConfig(
            redis_url="redis://localhost:6379/0",
            log_key="sentinel:shadow:comparisons",
            max_entries=100_000,
            rl_timeout_ms=50,
            action_utilities=(1.5, 0.8, 3.0),
        )
        self._lock = threading.RLock()
        self._pool = redis.ConnectionPool.from_url(
            self.config.redis_url,
            decode_responses=True,
            max_connections=16,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        self._logger = logging.getLogger(self.config.logger_name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(_JsonFormatter())
            self._logger.addHandler(handler)

    def log_comparison(
        self,
        *,
        asset_id: str,
        state: SentinelState,
        baseline_action: int,
        rl_action: int | None,
        confidence: float,
        status: str,
        baseline_result: Any = None,
        rl_result: Any = None,
        latency_ms: float = 0.0,
        extra: Mapping[str, Any] | None = None,
    ) -> ShadowRecord:
        record = ShadowRecord(
            asset_id=str(asset_id),
            baseline_action=int(baseline_action),
            rl_action=None if rl_action is None else int(rl_action),
            confidence=float(np.clip(confidence, 0.0, 1.0)),
            status=str(status),
            state_vector=tuple(float(x) for x in state.as_array().tolist()),
            baseline_result=_sanitize_for_json(baseline_result),
            rl_result=_sanitize_for_json(rl_result),
            latency_ms=float(max(0.0, latency_ms)),
            projected_reward=0.0,
        )

        projected_reward = self._projected_reward(record)
        payload = {
            "asset_id": record.asset_id,
            "baseline_action": record.baseline_action,
            "rl_action": record.rl_action,
            "confidence": record.confidence,
            "status": record.status,
            "state_vector": list(record.state_vector),
            "latency_ms": record.latency_ms,
            "projected_reward": projected_reward,
            "timestamp": record.timestamp,
        }
        if extra:
            payload.update({str(key): _sanitize_for_json(value) for key, value in extra.items()})

        serialized = json.dumps(payload, separators=(",", ":"), default=_json_default)
        with self._lock:
            try:
                self._client.rpush(self.config.log_key, serialized)
                if self.config.max_entries > 0:
                    self._client.ltrim(self.config.log_key, -self.config.max_entries, -1)
            except redis.RedisError as exc:  # pragma: no cover - network/runtime failures
                raise RuntimeError(f"Failed to persist shadow log to Redis: {exc}") from exc

        self._logger.info("shadow comparison", extra={"shadow_event": payload})
        return ShadowRecord(
            asset_id=record.asset_id,
            baseline_action=record.baseline_action,
            rl_action=record.rl_action,
            confidence=record.confidence,
            status=record.status,
            state_vector=record.state_vector,
            baseline_result=record.baseline_result,
            rl_result=record.rl_result,
            latency_ms=record.latency_ms,
            projected_reward=projected_reward,
            timestamp=record.timestamp,
        )

    def fetch_recent(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            try:
                raw_entries = self._client.lrange(self.config.log_key, 0, -1)
                if limit is not None and limit > 0:
                    raw_entries = raw_entries[-limit:]
            except redis.RedisError as exc:  # pragma: no cover - network/runtime failures
                raise RuntimeError(f"Failed to fetch shadow logs from Redis: {exc}") from exc

        parsed: list[dict[str, Any]] = []
        for entry in raw_entries:
            try:
                parsed.append(json.loads(entry))
            except json.JSONDecodeError:
                continue
        return parsed

    def close(self) -> None:
        with self._lock:
            try:
                self._client.close()
            finally:
                self._pool.disconnect(inuse_connections=True)

    def _projected_reward(self, record: ShadowRecord) -> float:
        if record.rl_action is None:
            return 0.0
        return _projected_reward(
            baseline_action=record.baseline_action,
            rl_action=record.rl_action,
            confidence=record.confidence,
            action_utilities=self.config.action_utilities,
        )


class ShadowExecutionManager:
    """Thread-safe shadow-mode gate for Sentinel asset processing."""

    def __init__(
        self,
        static_policy: Any,
        rl_policy: Any,
        logger: ShadowLogger | None = None,
        config: ShadowModeConfig | None = None,
    ) -> None:
        self.static_policy = static_policy
        self.rl_policy = rl_policy
        self.config = config or ShadowModeConfig()
        self.logger = logger or ShadowLogger(self.config)
        self._baseline_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-shadow")

    def process_asset(self, data: Mapping[str, Any]) -> Any:
        """Process a single asset through baseline production logic and shadow inference."""

        state = SentinelState.from_raw(data)
        asset_id = str(data.get("asset_id") or data.get("id") or data.get("assetId") or "unknown")

        shadow_start = time.perf_counter()
        rl_future = self._executor.submit(self._invoke_policy, self.rl_policy, state, data)

        with self._baseline_lock:
            baseline_result = self._invoke_policy(self.static_policy, state, data)

        baseline_action = _extract_action(baseline_result)
        if baseline_action is None:
            raise ValueError("Static policy did not return a valid action")

        rl_result: Any = None
        rl_action: int | None = None
        confidence = state.calibrated_confidence
        status = "shadow_complete"
        latency_ms = 0.0

        elapsed = time.perf_counter() - shadow_start
        remaining_timeout = max(0.0, (self.config.rl_timeout_ms / 1000.0) - elapsed)
        try:
            rl_result = rl_future.result(timeout=remaining_timeout)
            latency_ms = (time.perf_counter() - shadow_start) * 1000.0
            rl_action = _extract_action(rl_result)
            if rl_action is None:
                status = "shadow_error"
            else:
                confidence = _extract_confidence(rl_result, default=confidence)
        except FutureTimeoutError:
            latency_ms = (time.perf_counter() - shadow_start) * 1000.0
            status = "latency_error"
            rl_future.cancel()
        except Exception as exc:  # pragma: no cover - policy-specific failures
            latency_ms = (time.perf_counter() - shadow_start) * 1000.0
            status = "shadow_error"
            self.logger._logger.error(
                "shadow inference failure",
                extra={"shadow_event": {"asset_id": asset_id, "error": str(exc), "status": status}},
            )

        self.logger.log_comparison(
            asset_id=asset_id,
            state=state,
            baseline_action=baseline_action,
            rl_action=rl_action,
            confidence=confidence,
            status=status,
            baseline_result=baseline_result,
            rl_result=rl_result,
            latency_ms=latency_ms,
        )
        return baseline_result

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.logger.close()

    def __enter__(self) -> ShadowExecutionManager:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _invoke_policy(self, policy: Any, state: SentinelState, data: Mapping[str, Any]) -> Any:
        for method_name in ("process_asset", "predict_action", "act", "decide", "predict"):
            method = getattr(policy, method_name, None)
            if callable(method):
                return self._call_with_candidates(method, state, data)

        if callable(policy):
            return self._call_with_candidates(policy, state, data)

        raise TypeError("Policy object is not callable and exposes no supported inference method")

    def _call_with_candidates(self, fn: Any, state: SentinelState, data: Mapping[str, Any]) -> Any:
        candidates: tuple[tuple[Any, ...], ...] = (
            (state,),
            (data,),
            (state, data),
            (data, state),
        )
        last_error: Exception | None = None
        for args in candidates:
            try:
                return fn(*args)
            except TypeError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise TypeError("Policy invocation failed")


def _extract_action(result: Any) -> int | None:
    if result is None:
        return None
    if isinstance(result, (int, np.integer)):
        value = int(result)
        return value if value in {0, 1, 2} else None
    if isinstance(result, Mapping):
        for key in ("action", "decision", "label", "prediction"):
            if key in result:
                return _extract_action(result[key])
        if len(result) == 1:
            return _extract_action(next(iter(result.values())))
        return None
    for attr in ("action", "decision", "label", "prediction"):
        if hasattr(result, attr):
            return _extract_action(getattr(result, attr))
    if isinstance(result, Sequence) and not isinstance(result, (bytes, bytearray, str)) and result:
        return _extract_action(result[0])
    try:
        value = int(result)
    except (TypeError, ValueError):
        return None
    return value if value in {0, 1, 2} else None


def _extract_confidence(result: Any, default: float = 0.0) -> float:
    if result is None:
        return float(default)
    if isinstance(result, Mapping):
        for key in ("confidence", "score", "probability"):
            if key in result:
                return _coerce_float(result[key], default=default)
        probabilities = result.get("probabilities")
        if isinstance(probabilities, Mapping) and probabilities:
            return float(max((_coerce_float(v, default=0.0) for v in probabilities.values()), default=default))
    for attr in ("confidence", "score", "probability"):
        if hasattr(result, attr):
            return _coerce_float(getattr(result, attr), default=default)
    return float(default)


def _projected_reward(
    *,
    baseline_action: int,
    rl_action: int,
    confidence: float,
    action_utilities: tuple[float, float, float],
) -> float:
    baseline_score = action_utilities[baseline_action]
    rl_score = action_utilities[rl_action]
    return float(np.clip(confidence, 0.0, 1.0) * (rl_score - baseline_score))


def _coerce_action(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        candidate = int(value)
        return candidate if candidate in {0, 1, 2} else None
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return None
    return candidate if candidate in {0, 1, 2} else None


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _sanitize_for_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_sanitize_for_json(item) for item in value]
    return str(value)


def _json_default(value: Any) -> Any:
    return _sanitize_for_json(value)


__all__ = ["ShadowExecutionManager", "ShadowLogger", "ShadowMetrics", "ShadowModeConfig", "ShadowRecord"]

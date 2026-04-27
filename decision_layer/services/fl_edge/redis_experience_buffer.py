from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

import msgpack
import numpy as np
import redis  # type: ignore[reportMissingImports]


@dataclass(frozen=True)
class RedisExperienceBufferConfig:
    """Configuration for Redis-backed RL episode storage."""

    redis_url: str = "redis://localhost:6379/0"
    episodes_key: str = "sentinel:rl:episodes"
    weights_key: str = "sentinel:rl:episode_abs_returns"
    capacity: int = 50_000
    recent_window_size: int = 10_000
    max_connections: int = 64


class RedisExperienceBufferError(RuntimeError):
    """Raised when episode replay operations fail."""


class RedisExperienceBuffer:
    """Persistent Redis FIFO replay buffer with weighted sampling.

    Serialization:
    - Episodes are packed as MessagePack binary blobs.

    Sampling:
    - 90% from most recent `recent_window_size` episodes.
    - 10% from full buffer.
    - Priority weights are `abs(total_episode_return)`.
    """

    _APPEND_AND_TRIM_LUA = """
    local episodes_key = KEYS[1]
    local weights_key = KEYS[2]

    local episode_blob = ARGV[1]
    local abs_return = ARGV[2]
    local capacity = tonumber(ARGV[3])

    redis.call('RPUSH', episodes_key, episode_blob)
    redis.call('RPUSH', weights_key, abs_return)

    redis.call('LTRIM', episodes_key, -capacity, -1)
    redis.call('LTRIM', weights_key, -capacity, -1)

    return redis.call('LLEN', episodes_key)
    """

    def __init__(self, config: RedisExperienceBufferConfig | None = None, random_seed: int | None = None) -> None:
        self.config = config or RedisExperienceBufferConfig(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            episodes_key=os.getenv("RL_EPISODE_BUFFER_KEY", "sentinel:rl:episodes"),
            weights_key=os.getenv("RL_EPISODE_WEIGHTS_KEY", "sentinel:rl:episode_abs_returns"),
            capacity=int(os.getenv("RL_EPISODE_BUFFER_CAPACITY", "50000")),
            recent_window_size=int(os.getenv("RL_EPISODE_RECENT_WINDOW", "10000")),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "64")),
        )
        self._rng = np.random.default_rng(seed=random_seed)

        self._pool = redis.ConnectionPool.from_url(
            self.config.redis_url,
            decode_responses=False,
            max_connections=self.config.max_connections,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        self._append_and_trim_sha = self._client.script_load(self._APPEND_AND_TRIM_LUA)

    def add_episode(self, episode_data: Mapping[str, Any]) -> int:
        """Serialize and append an episode as a MessagePack blob into Redis FIFO."""

        prepared = self._prepare_episode(episode_data)
        episode_blob = msgpack.packb(prepared, use_bin_type=True)
        abs_return = float(abs(prepared["total_return"]))

        try:
            return int(
                self._client.evalsha(
                    self._append_and_trim_sha,
                    2,
                    self.config.episodes_key,
                    self.config.weights_key,
                    episode_blob,
                    f"{abs_return:.12f}",
                    str(self.config.capacity),
                )
            )
        except redis.exceptions.NoScriptError:
            self._append_and_trim_sha = self._client.script_load(self._APPEND_AND_TRIM_LUA)
            return int(
                self._client.evalsha(
                    self._append_and_trim_sha,
                    2,
                    self.config.episodes_key,
                    self.config.weights_key,
                    episode_blob,
                    f"{abs_return:.12f}",
                    str(self.config.capacity),
                )
            )
        except redis.RedisError as exc:  # pragma: no cover - network/runtime failures
            raise RedisExperienceBufferError(f"Failed to add episode to Redis buffer: {exc}") from exc

    def sample_batch(self, batch_size: int) -> list[dict[str, Any]]:
        """Sample a priority-weighted mixed batch from recent and full buffers."""

        if batch_size <= 0:
            return []

        try:
            total = int(self._client.llen(self.config.episodes_key))
        except redis.RedisError as exc:  # pragma: no cover
            raise RedisExperienceBufferError(f"Failed to get episode buffer size: {exc}") from exc

        if total <= 0:
            return []

        batch_size = min(batch_size, total)
        recent_target = int(np.floor(batch_size * 0.9))
        global_target = batch_size - recent_target

        recent_count = min(self.config.recent_window_size, total)
        recent_start = max(0, total - recent_count)

        recent_weights = self._get_weight_slice(start=recent_start, stop=-1)
        full_weights = self._get_weight_slice(start=0, stop=-1)

        recent_indices = self._weighted_sample_indices(
            weights=recent_weights,
            count=recent_target,
            offset=recent_start,
        )
        global_indices = self._weighted_sample_indices(
            weights=full_weights,
            count=global_target,
            offset=0,
        )

        sampled_indices = recent_indices + global_indices
        if len(sampled_indices) < batch_size:
            deficit = batch_size - len(sampled_indices)
            refill = self._weighted_sample_indices(weights=full_weights, count=deficit, offset=0)
            sampled_indices.extend(refill)

        blobs = self._fetch_episodes_by_indices(sampled_indices[:batch_size])
        unpacked: list[dict[str, Any]] = []
        for blob in blobs:
            try:
                unpacked.append(msgpack.unpackb(blob, raw=False, strict_map_key=False))
            except Exception as exc:  # pragma: no cover - corrupt payloads are rare
                raise RedisExperienceBufferError(f"Failed to unpack sampled episode: {exc}") from exc
        return unpacked

    def get_recent_buffer_stats(self) -> dict[str, Any]:
        """Return lightweight stats for observability of replay memory health."""

        try:
            total = int(self._client.llen(self.config.episodes_key))
        except redis.RedisError as exc:  # pragma: no cover
            raise RedisExperienceBufferError(f"Failed to get replay stats: {exc}") from exc

        if total <= 0:
            return {
                "size": 0,
                "capacity": self.config.capacity,
                "utilization": 0.0,
                "recent_window_size": 0,
                "recent_avg_abs_return": 0.0,
                "recent_max_abs_return": 0.0,
                "recent_min_abs_return": 0.0,
            }

        recent_count = min(self.config.recent_window_size, total)
        recent_start = max(0, total - recent_count)
        recent_weights = self._get_weight_slice(start=recent_start, stop=-1)
        if recent_weights.size == 0:
            recent_avg = 0.0
            recent_max = 0.0
            recent_min = 0.0
        else:
            recent_avg = float(np.mean(recent_weights))
            recent_max = float(np.max(recent_weights))
            recent_min = float(np.min(recent_weights))

        return {
            "size": total,
            "capacity": self.config.capacity,
            "utilization": float(total / max(1, self.config.capacity)),
            "recent_window_size": int(recent_count),
            "recent_avg_abs_return": recent_avg,
            "recent_max_abs_return": recent_max,
            "recent_min_abs_return": recent_min,
        }

    def close(self) -> None:
        """Close Redis client and connection pool."""

        try:
            self._client.close()
        finally:
            self._pool.disconnect(inuse_connections=True)

    def _prepare_episode(self, episode_data: Mapping[str, Any]) -> dict[str, Any]:
        rewards_raw = episode_data.get("rewards", [])
        rewards: list[float]
        if isinstance(rewards_raw, (list, tuple)):
            rewards = [float(x) for x in rewards_raw]
        elif rewards_raw is None:
            rewards = []
        else:
            rewards = [float(rewards_raw)]

        total_return = episode_data.get("total_return")
        if total_return is None:
            total_return_value = float(sum(rewards))
        else:
            total_return_value = float(total_return)

        prepared = {
            "states": self._to_serializable(episode_data.get("states", [])),
            "actions": self._to_serializable(episode_data.get("actions", [])),
            "rewards": rewards,
            "next_states": self._to_serializable(episode_data.get("next_states", [])),
            "dones": self._to_serializable(episode_data.get("dones", [])),
            "infos": self._to_serializable(episode_data.get("infos", [])),
            "total_return": total_return_value,
            "abs_return": float(abs(total_return_value)),
            "created_at_ms": int(episode_data.get("created_at_ms", int(time.time() * 1000))),
            "metadata": self._to_serializable(episode_data.get("metadata", {})),
        }
        return prepared

    def _get_weight_slice(self, start: int, stop: int) -> np.ndarray:
        try:
            raw = self._client.lrange(self.config.weights_key, start, stop)
        except redis.RedisError as exc:  # pragma: no cover
            raise RedisExperienceBufferError(f"Failed to read episode weights: {exc}") from exc

        weights: list[float] = []
        for item in raw:
            try:
                if isinstance(item, bytes):
                    weights.append(float(item.decode("utf-8")))
                else:
                    weights.append(float(item))
            except (TypeError, ValueError):
                weights.append(0.0)
        return np.asarray(weights, dtype=np.float64)

    def _weighted_sample_indices(self, weights: np.ndarray, count: int, offset: int = 0) -> list[int]:
        if count <= 0 or weights.size == 0:
            return []

        size = int(weights.size)
        replace = count > size

        clipped = np.clip(weights, a_min=0.0, a_max=None)
        total_weight = float(np.sum(clipped))

        if total_weight <= 0.0:
            chosen = self._rng.choice(size, size=count, replace=replace)
        else:
            probs = clipped / total_weight
            chosen = self._rng.choice(size, size=count, replace=replace, p=probs)

        return [int(x) + int(offset) for x in np.asarray(chosen).tolist()]

    def _fetch_episodes_by_indices(self, indices: list[int]) -> list[bytes]:
        if not indices:
            return []

        try:
            pipe = self._client.pipeline(transaction=False)
            for idx in indices:
                pipe.lindex(self.config.episodes_key, idx)
            result = pipe.execute()
        except redis.RedisError as exc:  # pragma: no cover
            raise RedisExperienceBufferError(f"Failed to fetch sampled episodes: {exc}") from exc

        blobs: list[bytes] = []
        for item in result:
            if item is None:
                continue
            if isinstance(item, bytes):
                blobs.append(item)
            else:
                blobs.append(bytes(item))
        return blobs

    @staticmethod
    def _to_serializable(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return value.astype(np.float32).tolist()
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, Mapping):
            return {str(k): RedisExperienceBuffer._to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [RedisExperienceBuffer._to_serializable(v) for v in value]
        return value


__all__ = ["RedisExperienceBuffer", "RedisExperienceBufferConfig", "RedisExperienceBufferError"]

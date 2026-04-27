from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any

import redis  # type: ignore[reportMissingImports]


@dataclass(frozen=True)
class RedisBufferConfig:
    """Configuration contract for the Redis-backed training buffer."""

    redis_url: str = "redis://localhost:6379/0"
    list_key: str = "hitl:training_buffer"
    trigger_channel: str = "trigger_fl"


class TrainingBufferError(RuntimeError):
    """Base exception for all training buffer operations."""


class TrainingBuffer:
    """Redis-backed queue used by FL orchestration components.

    Key guarantees:
    - Uses `RPUSH` for ingestion.
    - Uses an atomic Lua script to fetch-and-clear items in one server-side operation.
    - Uses isolated pub/sub connections guarded by a lock to avoid cross-thread misuse.
    """

    _GET_AND_CLEAR_LUA = """
    local key = KEYS[1]
    local values = redis.call('LRANGE', key, 0, -1)
    redis.call('DEL', key)
    return values
    """

    def __init__(self, config: RedisBufferConfig | None = None) -> None:
        self.config = config or RedisBufferConfig(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            list_key=os.getenv("HITL_BUFFER_KEY", "hitl:training_buffer"),
            trigger_channel=os.getenv("FL_TRIGGER_CHANNEL", "trigger_fl"),
        )
        self._client = redis.Redis.from_url(self.config.redis_url, decode_responses=True)
        self._pubsub_client = redis.Redis.from_url(self.config.redis_url, decode_responses=True)
        self._pubsub_lock = threading.Lock()
        self._get_and_clear_sha = self._client.script_load(self._GET_AND_CLEAR_LUA)

    @property
    def list_key(self) -> str:
        return self.config.list_key

    def push_sample(self, sample: dict[str, Any] | str) -> int:
        """Serialize sample and append it to buffer via `RPUSH`.

        Returns:
            New list size after append.
        """
        payload = sample if isinstance(sample, str) else json.dumps(sample, separators=(",", ":"))
        try:
            return int(self._client.rpush(self.config.list_key, payload))
        except redis.RedisError as exc:  # pragma: no cover - network/runtime
            raise TrainingBufferError(f"Failed to push sample into Redis list: {exc}") from exc

    def length(self) -> int:
        """Return current buffered sample count."""
        try:
            return int(self._client.llen(self.config.list_key))
        except redis.RedisError as exc:  # pragma: no cover - network/runtime
            raise TrainingBufferError(f"Failed to read Redis list length: {exc}") from exc

    def get_and_clear(self) -> list[dict[str, Any]]:
        """Atomically retrieve all buffered samples and clear the list.

        The operation is executed as one Lua script to avoid race conditions
        between workers that could otherwise read stale/interleaved buffers.
        """
        try:
            raw_values = self._client.evalsha(self._get_and_clear_sha, 1, self.config.list_key)
        except redis.exceptions.NoScriptError:
            self._get_and_clear_sha = self._client.script_load(self._GET_AND_CLEAR_LUA)
            raw_values = self._client.evalsha(self._get_and_clear_sha, 1, self.config.list_key)
        except redis.RedisError as exc:  # pragma: no cover - network/runtime
            raise TrainingBufferError(f"Failed to atomically get+clear training buffer: {exc}") from exc

        parsed: list[dict[str, Any]] = []
        for item in raw_values:
            try:
                parsed.append(json.loads(item))
            except json.JSONDecodeError:
                parsed.append({"raw": item})
        return parsed

    def publish_trigger(self, message: dict[str, Any] | str) -> int:
        """Publish a trigger event using a thread-safe lock around Redis publish."""
        payload = message if isinstance(message, str) else json.dumps(message, separators=(",", ":"))
        with self._pubsub_lock:
            try:
                return int(self._pubsub_client.publish(self.config.trigger_channel, payload))
            except redis.RedisError as exc:  # pragma: no cover - network/runtime
                raise TrainingBufferError(f"Failed to publish FL trigger: {exc}") from exc

    def create_subscriber(self) -> redis.client.PubSub:
        """Create a dedicated subscriber object for the trigger channel.

        Callers must consume this subscriber in a single thread/task.
        """
        with self._pubsub_lock:
            try:
                subscriber = self._pubsub_client.pubsub(ignore_subscribe_messages=True)
                subscriber.subscribe(self.config.trigger_channel)
                return subscriber
            except redis.RedisError as exc:  # pragma: no cover - network/runtime
                raise TrainingBufferError(f"Failed to create trigger subscriber: {exc}") from exc

    def close(self) -> None:
        """Close all Redis clients associated with this helper."""
        try:
            self._client.close()
        finally:
            self._pubsub_client.close()

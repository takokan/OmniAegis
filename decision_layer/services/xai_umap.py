from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import redis  # type: ignore[reportMissingImports]

try:
    from umap import UMAP
except ImportError:  # pragma: no cover
    UMAP = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class UMAPProjectionConfig:
    """Configuration for UMAP embedding projection."""

    redis_url: str = "redis://localhost:6379/0"
    max_connections: int = 16
    cache_ttl_seconds: int = 86400
    n_neighbors: int = 15
    min_dist: float = 0.1
    metric: str = "euclidean"
    random_state: int = 42

    @classmethod
    def from_env(cls) -> UMAPProjectionConfig:
        return cls(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "16")),
            cache_ttl_seconds=int(os.getenv("UMAP_CACHE_TTL_SECONDS", "86400")),
            n_neighbors=int(os.getenv("UMAP_N_NEIGHBORS", "15")),
            min_dist=float(os.getenv("UMAP_MIN_DIST", "0.1")),
            metric=os.getenv("UMAP_METRIC", "euclidean"),
            random_state=int(os.getenv("UMAP_RANDOM_STATE", "42")),
        )


class UMAPProjectionError(RuntimeError):
    """Raised when UMAP projection operations fail."""


class UMAPProjector:
    """UMAP projector with Redis caching for 512D → 2D embedding reduction."""

    def __init__(self, config: UMAPProjectionConfig | None = None) -> None:
        if UMAP is None:
            raise UMAPProjectionError("umap-learn not installed")

        self.config = config or UMAPProjectionConfig.from_env()

        self._pool = redis.ConnectionPool.from_url(
            self.config.redis_url,
            decode_responses=True,
            max_connections=self.config.max_connections,
        )
        self._client = redis.Redis(connection_pool=self._pool)

        self._umap = UMAP(
            n_components=2,
            n_neighbors=self.config.n_neighbors,
            min_dist=self.config.min_dist,
            metric=self.config.metric,
            random_state=self.config.random_state,
        )

    @classmethod
    def from_env(cls) -> UMAPProjector:
        """Create instance from environment variables."""
        config = UMAPProjectionConfig.from_env()
        return cls(config=config)

    def close(self) -> None:
        """Close Redis connection pool."""
        try:
            self._client.close()
        finally:
            self._pool.disconnect(inuse_connections=True)

    def project(
        self,
        embeddings: list[list[float]] | np.ndarray,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        """Project 512D embeddings to 2D UMAP space with caching.

        Args:
            embeddings: List of 512-dimensional vectors or numpy array.
            cache_key: Optional cache key. If None, auto-generated from hash.

        Returns:
            Dict with projected_2d (list of [x, y]), and metadata.
        """

        embeddings_array = np.asarray(embeddings, dtype=np.float32)

        if embeddings_array.ndim != 2 or embeddings_array.shape[1] != 512:
            raise UMAPProjectionError(f"Expected shape (N, 512), got {embeddings_array.shape}")

        if cache_key is None:
            content_hash = hashlib.sha256(embeddings_array.tobytes()).hexdigest()
            cache_key = f"umap:projection:{content_hash}"

        try:
            cached = self._client.get(cache_key)
            if cached:
                payload = json.loads(cached)
                payload["cached"] = True
                return payload
        except redis.RedisError:
            pass

        try:
            projected = self._umap.fit_transform(embeddings_array)
        except Exception as exc:  # pragma: no cover
            raise UMAPProjectionError(f"UMAP fit_transform failed: {exc}") from exc

        projected_2d = projected.tolist()

        result = {
            "projected_2d": projected_2d,
            "count": len(projected_2d),
            "dimensions": 2,
            "metric": self.config.metric,
            "cached": False,
            "generated_at_ms": int(time.time() * 1000),
        }

        try:
            self._client.set(
                cache_key,
                json.dumps(result),
                ex=self.config.cache_ttl_seconds,
            )
        except redis.RedisError:
            pass

        return result


__all__ = [
    "UMAPProjector",
    "UMAPProjectionConfig",
    "UMAPProjectionError",
]

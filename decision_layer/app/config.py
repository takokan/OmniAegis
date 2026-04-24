from __future__ import annotations

import os
from dataclasses import dataclass

from qdrant_client import QdrantClient


@dataclass(frozen=True)
class QdrantSettings:
    mode: str = "local"  # local | remote
    local_path: str = "./.qdrant"
    url: str | None = None
    host: str = "localhost"
    port: int = 6333
    api_key: str | None = None
    collection_name: str = "semantic_assets"
    hnsw_m: int = 16
    hnsw_ef_construct: int = 128


class QdrantClientSingleton:
    _client: QdrantClient | None = None

    @classmethod
    def get_client(cls, settings: QdrantSettings) -> QdrantClient:
        if cls._client is not None:
            return cls._client

        if settings.mode == "remote":
            if settings.url:
                cls._client = QdrantClient(url=settings.url, api_key=settings.api_key)
            else:
                cls._client = QdrantClient(
                    host=settings.host,
                    port=settings.port,
                    api_key=settings.api_key,
                )
        else:
            cls._client = QdrantClient(path=settings.local_path)

        return cls._client

    @classmethod
    def close_client(cls) -> None:
        if cls._client is not None:
            cls._client.close()
            cls._client = None


def load_qdrant_settings() -> QdrantSettings:
    return QdrantSettings(
        mode=os.getenv("QDRANT_MODE", "local").strip().lower(),
        local_path=os.getenv("QDRANT_LOCAL_PATH", "./.qdrant"),
        url=os.getenv("QDRANT_URL") or None,
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
        api_key=os.getenv("QDRANT_API_KEY") or None,
        collection_name=os.getenv("QDRANT_COLLECTION", "semantic_assets"),
        hnsw_m=int(os.getenv("QDRANT_HNSW_M", "16")),
        hnsw_ef_construct=int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "128")),
    )

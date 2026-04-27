from __future__ import annotations

import os
from dataclasses import dataclass

from qdrant_client import QdrantClient


@dataclass(frozen=True)
class QdrantSettings:
    url: str
    api_key: str
    collection_name: str = "semantic_assets"
    hnsw_m: int = 16
    hnsw_ef_construct: int = 128


class QdrantClientSingleton:
    _client: QdrantClient | None = None

    @classmethod
    def get_client(cls, settings: QdrantSettings) -> QdrantClient:
        if cls._client is not None:
            return cls._client

        cls._client = QdrantClient(url=settings.url, api_key=settings.api_key)

        return cls._client

    @classmethod
    def close_client(cls) -> None:
        if cls._client is not None:
            cls._client.close()
            cls._client = None


def load_qdrant_settings() -> QdrantSettings:
    url = (os.getenv("QDRANT_URL") or "").strip()
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip()

    if not url:
        raise RuntimeError("QDRANT_URL is required for cloud Qdrant")
    if not api_key:
        raise RuntimeError("QDRANT_API_KEY is required for cloud Qdrant")

    return QdrantSettings(
        url=url,
        api_key=api_key,
        collection_name=os.getenv("QDRANT_COLLECTION", "semantic_assets"),
        hnsw_m=int(os.getenv("QDRANT_HNSW_M", "16")),
        hnsw_ef_construct=int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "128")),
    )

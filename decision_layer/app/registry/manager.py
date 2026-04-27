from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import Lock
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


@dataclass
class MatchResult:
    asset_id: str
    confidence: float
    distance_or_similarity: float
    metadata: dict[str, Any]


class RegistryManager:
    """Qdrant-backed registry for real-time matching and long-term retrieval.

    - Image/Video: 64D binary fingerprint vectors stored in Qdrant.
    - Audio: normalized embedding vectors stored in Qdrant.
    - Semantic image vectors: normalized embeddings stored in Qdrant.
    """

    def __init__(
        self,
        audio_dim: int,
        semantic_dim: int = 512,
        qdrant_client: QdrantClient | None = None,
        image_collection_name: str = "image_assets",
        video_collection_name: str = "video_assets",
        audio_collection_name: str = "audio_assets",
        semantic_collection_name: str = "semantic_assets",
        hnsw_m: int = 16,
        hnsw_ef_construct: int = 128,
    ) -> None:
        self._lock = Lock()

        self.image_dim = 64
        self.video_dim = 64
        self.audio_dim = audio_dim
        self.semantic_dim = semantic_dim
        self.qdrant = qdrant_client
        self.image_collection_name = image_collection_name
        self.video_collection_name = video_collection_name
        self.audio_collection_name = audio_collection_name
        self.semantic_collection_name = semantic_collection_name
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct

        self.semantic_ids: list[str] = []

        self.metadata_store: dict[str, dict[str, Any]] = {}

        if self.qdrant is not None:
            self._ensure_collection(self.image_collection_name, self.image_dim)
            self._ensure_collection(self.video_collection_name, self.video_dim)
            self._ensure_collection(self.audio_collection_name, self.audio_dim)
            self._ensure_semantic_collection()

    def _ensure_collection(self, collection_name: str, vector_size: int) -> None:
        if self.qdrant is None:
            return

        existing = {c.name for c in self.qdrant.get_collections().collections}
        if collection_name in existing:
            return

        self.qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=vector_size,
                distance=qmodels.Distance.COSINE,
                on_disk=True,
            ),
            hnsw_config=qmodels.HnswConfigDiff(
                m=self.hnsw_m,
                ef_construct=self.hnsw_ef_construct,
                on_disk=True,
            ),
        )

    def _ensure_semantic_collection(self) -> None:
        self._ensure_collection(self.semantic_collection_name, self.semantic_dim)

    @staticmethod
    def _to_binary_row(hash_bytes: np.ndarray) -> np.ndarray:
        row = np.asarray(hash_bytes, dtype=np.uint8).reshape(1, -1)
        if row.shape[1] != 8:
            raise ValueError("Binary fingerprint must be exactly 64 bits (8 bytes)")
        return row

    @staticmethod
    def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-8
        return vectors / norms

    @staticmethod
    def _binary_hash_to_vector(hash_bytes: np.ndarray) -> np.ndarray:
        row = np.asarray(hash_bytes, dtype=np.uint8).reshape(-1)
        if row.shape[0] != 8:
            raise ValueError("Binary fingerprint must be exactly 64 bits (8 bytes)")
        bits = np.unpackbits(row).astype(np.float32)
        return bits

    @staticmethod
    def _semantic_point_id(asset_id: str) -> int:
        """Return a deterministic integer point id compatible with Qdrant.

        Qdrant validates string ids as UUIDs. Using a stable int id avoids UUID
        requirements while preserving asset identity in payload.
        """
        digest = hashlib.sha1(asset_id.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=False)

    @staticmethod
    def _build_query_filter(
        owner_user_id: str | None = None,
        modality_filter: str | None = None,
    ) -> qmodels.Filter | None:
        conditions: list[qmodels.FieldCondition] = []

        if owner_user_id:
            conditions.append(
                qmodels.FieldCondition(
                    key="user_id",
                    match=qmodels.MatchValue(value=owner_user_id),
                )
            )

        if modality_filter:
            conditions.append(
                qmodels.FieldCondition(
                    key="modality",
                    match=qmodels.MatchValue(value=modality_filter),
                )
            )

        if not conditions:
            return None

        return qmodels.Filter(must=conditions)

    def register_image(self, asset_id: str, hash_bytes: np.ndarray, metadata: dict[str, Any]) -> None:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            vector = self._binary_hash_to_vector(hash_bytes)
            payload = {"asset_id": asset_id, **metadata}

            self.qdrant.upsert(
                collection_name=self.image_collection_name,
                points=[
                    qmodels.PointStruct(
                        id=self._semantic_point_id(asset_id),
                        vector=vector.tolist(),
                        payload=payload,
                    )
                ],
                wait=False,
            )

            existing = self.metadata_store.get(asset_id, {})
            self.metadata_store[asset_id] = {**existing, **metadata}

    def register_video(self, asset_id: str, hash_bytes: np.ndarray, metadata: dict[str, Any]) -> None:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            vector = self._binary_hash_to_vector(hash_bytes)
            payload = {"asset_id": asset_id, **metadata}

            self.qdrant.upsert(
                collection_name=self.video_collection_name,
                points=[
                    qmodels.PointStruct(
                        id=self._semantic_point_id(asset_id),
                        vector=vector.tolist(),
                        payload=payload,
                    )
                ],
                wait=False,
            )

            existing = self.metadata_store.get(asset_id, {})
            self.metadata_store[asset_id] = {**existing, **metadata}

    def register_audio(self, asset_id: str, embedding: np.ndarray, metadata: dict[str, Any]) -> None:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            row = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            row = self._normalize_rows(row)

            payload = {"asset_id": asset_id, **metadata}

            self.qdrant.upsert(
                collection_name=self.audio_collection_name,
                points=[
                    qmodels.PointStruct(
                        id=self._semantic_point_id(asset_id),
                        vector=row[0].tolist(),
                        payload=payload,
                    )
                ],
                wait=False,
            )

            existing = self.metadata_store.get(asset_id, {})
            self.metadata_store[asset_id] = {**existing, **metadata}

    def register_semantic(self, asset_id: str, embedding: np.ndarray, metadata: dict[str, Any]) -> None:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            row = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            row = self._normalize_rows(row)

            payload = {
                "asset_id": asset_id,
                **metadata,
            }

            self.qdrant.upsert(
                collection_name=self.semantic_collection_name,
                points=[
                    qmodels.PointStruct(
                        id=self._semantic_point_id(asset_id),
                        vector=row[0].tolist(),
                        payload=payload,
                    )
                ],
                wait=False,
            )

            if asset_id not in self.semantic_ids:
                self.semantic_ids.append(asset_id)
            existing = self.metadata_store.get(asset_id, {})
            self.metadata_store[asset_id] = {**existing, **metadata}

    def match_image(
        self,
        hash_bytes: np.ndarray,
        top_k: int = 5,
        owner_user_id: str | None = None,
    ) -> list[MatchResult]:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            query = self._binary_hash_to_vector(hash_bytes)

            response = self.qdrant.query_points(
                collection_name=self.image_collection_name,
                query=query.tolist(),
                limit=top_k,
                query_filter=self._build_query_filter(owner_user_id=owner_user_id),
                with_payload=True,
                with_vectors=False,
            )
            points = response.points

            results: list[MatchResult] = []
            for point in points:
                payload = dict(point.payload or {})
                asset_id = str(payload.get("asset_id") or point.id)
                score = float(point.score)
                confidence = max(0.0, min(1.0, (score + 1.0) / 2.0))
                results.append(
                    MatchResult(
                        asset_id=asset_id,
                        confidence=confidence,
                        distance_or_similarity=score,
                        metadata=payload,
                    )
                )
            return results

    def match_video(
        self,
        hash_bytes: np.ndarray,
        top_k: int = 5,
        owner_user_id: str | None = None,
    ) -> list[MatchResult]:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            query = self._binary_hash_to_vector(hash_bytes)

            response = self.qdrant.query_points(
                collection_name=self.video_collection_name,
                query=query.tolist(),
                limit=top_k,
                query_filter=self._build_query_filter(owner_user_id=owner_user_id),
                with_payload=True,
                with_vectors=False,
            )
            points = response.points

            results: list[MatchResult] = []
            for point in points:
                payload = dict(point.payload or {})
                asset_id = str(payload.get("asset_id") or point.id)
                score = float(point.score)
                confidence = max(0.0, min(1.0, (score + 1.0) / 2.0))
                results.append(
                    MatchResult(
                        asset_id=asset_id,
                        confidence=confidence,
                        distance_or_similarity=score,
                        metadata=payload,
                    )
                )
            return results

    def match_audio(
        self,
        embedding: np.ndarray,
        top_k: int = 5,
        owner_user_id: str | None = None,
    ) -> list[MatchResult]:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            query = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            query = self._normalize_rows(query)

            response = self.qdrant.query_points(
                collection_name=self.audio_collection_name,
                query=query[0].tolist(),
                limit=top_k,
                query_filter=self._build_query_filter(owner_user_id=owner_user_id),
                with_payload=True,
                with_vectors=False,
            )
            points = response.points

            results: list[MatchResult] = []
            for point in points:
                payload = dict(point.payload or {})
                asset_id = str(payload.get("asset_id") or point.id)
                score = float(point.score)
                confidence = max(0.0, min(1.0, (score + 1.0) / 2.0))
                results.append(
                    MatchResult(
                        asset_id=asset_id,
                        confidence=confidence,
                        distance_or_similarity=score,
                        metadata=payload,
                    )
                )
            return results

    def match_semantic(
        self,
        embedding: np.ndarray,
        top_k: int = 5,
        modality_filter: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[MatchResult]:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            query = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            query = self._normalize_rows(query)

            query_filter = self._build_query_filter(
                owner_user_id=owner_user_id,
                modality_filter=modality_filter,
            )

            if hasattr(self.qdrant, "query_points"):
                response = self.qdrant.query_points(
                    collection_name=self.semantic_collection_name,
                    query=query[0].tolist(),
                    limit=top_k,
                    query_filter=query_filter,
                    with_payload=True,
                    with_vectors=False,
                )
                points = response.points
            else:
                points = self.qdrant.search(
                    collection_name=self.semantic_collection_name,
                    query_vector=query[0].tolist(),
                    limit=top_k,
                    query_filter=query_filter,
                    with_payload=True,
                    with_vectors=False,
                )

            results: list[MatchResult] = []
            for point in points:
                payload = dict(point.payload or {})
                asset_id = str(payload.get("asset_id") or point.id)
                score = float(point.score)
                confidence = max(0.0, min(1.0, (score + 1.0) / 2.0))
                results.append(
                    MatchResult(
                        asset_id=asset_id,
                        confidence=confidence,
                        distance_or_similarity=score,
                        metadata=payload,
                    )
                )
            return results

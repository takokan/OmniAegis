from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

import faiss
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
    """In-memory FAISS-backed registry for real-time matching.

    - Image/Video: Hamming search with `IndexBinaryFlat(64)`.
    - Audio: Cosine search with `IndexFlatIP` over normalized embeddings.
    - Semantic image vectors: Qdrant HNSW index with cosine distance.
    """

    def __init__(
        self,
        audio_dim: int,
        semantic_dim: int = 512,
        qdrant_client: QdrantClient | None = None,
        semantic_collection_name: str = "semantic_assets",
        hnsw_m: int = 16,
        hnsw_ef_construct: int = 128,
    ) -> None:
        self._lock = Lock()

        self.image_index = faiss.IndexBinaryFlat(64)
        self.video_index = faiss.IndexBinaryFlat(64)
        self.audio_index = faiss.IndexFlatIP(audio_dim)
        self.semantic_dim = semantic_dim
        self.qdrant = qdrant_client
        self.semantic_collection_name = semantic_collection_name
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct

        self.image_ids: list[str] = []
        self.video_ids: list[str] = []
        self.audio_ids: list[str] = []
        self.semantic_ids: list[str] = []

        self.metadata_store: dict[str, dict[str, Any]] = {}

        if self.qdrant is not None:
            self._ensure_semantic_collection()

    def _ensure_semantic_collection(self) -> None:
        if self.qdrant is None:
            return

        existing = {c.name for c in self.qdrant.get_collections().collections}
        if self.semantic_collection_name in existing:
            return

        self.qdrant.create_collection(
            collection_name=self.semantic_collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.semantic_dim,
                distance=qmodels.Distance.COSINE,
                on_disk=True,
            ),
            hnsw_config=qmodels.HnswConfigDiff(
                m=self.hnsw_m,
                ef_construct=self.hnsw_ef_construct,
                on_disk=True,
            ),
        )

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

    def register_image(self, asset_id: str, hash_bytes: np.ndarray, metadata: dict[str, Any]) -> None:
        with self._lock:
            row = self._to_binary_row(hash_bytes)
            self.image_index.add(row)
            self.image_ids.append(asset_id)
            self.metadata_store[asset_id] = metadata

    def register_video(self, asset_id: str, hash_bytes: np.ndarray, metadata: dict[str, Any]) -> None:
        with self._lock:
            row = self._to_binary_row(hash_bytes)
            self.video_index.add(row)
            self.video_ids.append(asset_id)
            self.metadata_store[asset_id] = metadata

    def register_audio(self, asset_id: str, embedding: np.ndarray, metadata: dict[str, Any]) -> None:
        with self._lock:
            row = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            row = self._normalize_rows(row)
            self.audio_index.add(row)
            self.audio_ids.append(asset_id)
            self.metadata_store[asset_id] = metadata

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
                        id=asset_id,
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

    def match_image(self, hash_bytes: np.ndarray, top_k: int = 5) -> list[MatchResult]:
        with self._lock:
            if self.image_index.ntotal == 0:
                return []

            query = self._to_binary_row(hash_bytes)
            k = min(top_k, self.image_index.ntotal)
            distances, indices = self.image_index.search(query, k)

            results: list[MatchResult] = []
            for dist, idx in zip(distances[0], indices[0], strict=False):
                if idx < 0:
                    continue
                asset_id = self.image_ids[idx]
                confidence = max(0.0, 1.0 - (float(dist) / 64.0))
                results.append(
                    MatchResult(
                        asset_id=asset_id,
                        confidence=confidence,
                        distance_or_similarity=float(dist),
                        metadata=self.metadata_store.get(asset_id, {}),
                    )
                )
            return results

    def match_video(self, hash_bytes: np.ndarray, top_k: int = 5) -> list[MatchResult]:
        with self._lock:
            if self.video_index.ntotal == 0:
                return []

            query = self._to_binary_row(hash_bytes)
            k = min(top_k, self.video_index.ntotal)
            distances, indices = self.video_index.search(query, k)

            results: list[MatchResult] = []
            for dist, idx in zip(distances[0], indices[0], strict=False):
                if idx < 0:
                    continue
                asset_id = self.video_ids[idx]
                confidence = max(0.0, 1.0 - (float(dist) / 64.0))
                results.append(
                    MatchResult(
                        asset_id=asset_id,
                        confidence=confidence,
                        distance_or_similarity=float(dist),
                        metadata=self.metadata_store.get(asset_id, {}),
                    )
                )
            return results

    def match_audio(self, embedding: np.ndarray, top_k: int = 5) -> list[MatchResult]:
        with self._lock:
            if self.audio_index.ntotal == 0:
                return []

            query = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            query = self._normalize_rows(query)
            k = min(top_k, self.audio_index.ntotal)
            similarities, indices = self.audio_index.search(query, k)

            results: list[MatchResult] = []
            for sim, idx in zip(similarities[0], indices[0], strict=False):
                if idx < 0:
                    continue
                asset_id = self.audio_ids[idx]
                confidence = max(0.0, min(1.0, (float(sim) + 1.0) / 2.0))
                results.append(
                    MatchResult(
                        asset_id=asset_id,
                        confidence=confidence,
                        distance_or_similarity=float(sim),
                        metadata=self.metadata_store.get(asset_id, {}),
                    )
                )
            return results

    def match_semantic(
        self,
        embedding: np.ndarray,
        top_k: int = 5,
        modality_filter: str | None = None,
    ) -> list[MatchResult]:
        if self.qdrant is None:
            raise RuntimeError("Qdrant client is not initialized")

        with self._lock:
            query = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            query = self._normalize_rows(query)

            query_filter = None
            if modality_filter:
                query_filter = qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="modality",
                            match=qmodels.MatchValue(value=modality_filter),
                        )
                    ]
                )

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

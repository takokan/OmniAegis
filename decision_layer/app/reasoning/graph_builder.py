from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import torch
from torch_geometric.data import HeteroData
from torch_geometric.transforms import ToUndirected


class GraphBuilder:
    """Builds on-the-fly heterogeneous subgraphs for reasoning.

    Node types:
    - Asset (512-d embedding)
    - Creator (trust_score, tenure_months_normalized)
    - Licensee (license_status)

    Edge types:
    - Asset -> Creator: created_by
    - Asset -> Licensee: licensed_to
    - Asset -> Asset: similar_to (weighted by semantic similarity)
    - Asset -> Asset: flagged_with (weighted, stronger negative signal)
    """

    def __init__(self, flagged_edge_boost: float = 1.5, graph_db: Any | None = None) -> None:
        self.flagged_edge_boost = flagged_edge_boost
        self._to_undirected = ToUndirected(merge=False)
        self.graph_db = graph_db

    @staticmethod
    def _normalize_tenure(tenure_months: float) -> float:
        # Assumes 10 years as soft max for normalization.
        return float(np.clip(tenure_months / 120.0, 0.0, 1.0))

    @staticmethod
    def _metadata_from_result(result: Any) -> tuple[str, float, dict[str, Any]]:
        if isinstance(result, dict):
            asset_id = str(result.get("asset_id", ""))
            similarity = float(result.get("score", 0.0))
            metadata = dict(result.get("metadata", {}))
            return asset_id, similarity, metadata

        asset_id = str(getattr(result, "asset_id", ""))
        similarity = float(getattr(result, "distance_or_similarity", 0.0))
        metadata = dict(getattr(result, "metadata", {}) or {})
        return asset_id, similarity, metadata

    @staticmethod
    def _safe_embedding(metadata: dict[str, Any], fallback: np.ndarray, similarity: float) -> np.ndarray:
        candidate = metadata.get("semantic_embedding")
        if candidate is not None:
            arr = np.asarray(candidate, dtype=np.float32).reshape(-1)
            if arr.shape[0] == 512:
                return arr

        # Fallback: scaled proxy vector if neighbor embedding is not available in metadata.
        scale = float(np.clip((similarity + 1.0) / 2.0, 0.0, 1.0))
        return (fallback * scale).astype(np.float32)

    def build_subgraph(
        self,
        query_embedding: np.ndarray,
        qdrant_results: Iterable[Any],
        query_metadata: dict[str, Any] | None = None,
    ) -> HeteroData:
        query_metadata = query_metadata or {}

        query_vec = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        if query_vec.shape[0] != 512:
            raise ValueError("Query embedding must be 512-dimensional")

        asset_ids: list[str] = ["__query__"]
        asset_features: list[np.ndarray] = [query_vec]

        creator_ids: list[str] = []
        creator_features: list[list[float]] = []

        licensee_ids: list[str] = []
        licensee_features: list[list[float]] = []

        created_edges: list[list[int]] = []
        created_attr: list[list[float]] = []

        licensed_edges: list[list[int]] = []
        licensed_attr: list[list[float]] = []

        similar_edges: list[list[int]] = []
        similar_attr: list[list[float]] = []

        flagged_edges: list[list[int]] = []
        flagged_attr: list[list[float]] = []

        creator_index: dict[str, int] = {}
        licensee_index: dict[str, int] = {}

        def upsert_creator(creator_id: str, trust_score: float, tenure_months: float) -> int:
            if creator_id in creator_index:
                return creator_index[creator_id]
            idx = len(creator_ids)
            creator_index[creator_id] = idx
            creator_ids.append(creator_id)
            creator_features.append(
                [
                    float(np.clip(trust_score, 0.0, 1.0)),
                    self._normalize_tenure(float(tenure_months)),
                ]
            )
            return idx

        def upsert_licensee(licensee_id: str, status: float) -> int:
            if licensee_id in licensee_index:
                return licensee_index[licensee_id]
            idx = len(licensee_ids)
            licensee_index[licensee_id] = idx
            licensee_ids.append(licensee_id)
            licensee_features.append([float(np.clip(status, 0.0, 1.0))])
            return idx

        # Attach query creator/license info if available.
        if "creator_id" in query_metadata:
            c_idx = upsert_creator(
                str(query_metadata.get("creator_id")),
                float(query_metadata.get("creator_trust_score", 0.5)),
                float(query_metadata.get("creator_tenure_months", 12.0)),
            )
            created_edges.append([0, c_idx])
            created_attr.append([0.3])

        if "licensee_id" in query_metadata:
            l_idx = upsert_licensee(
                str(query_metadata.get("licensee_id")),
                float(query_metadata.get("license_status", 0.0)),
            )
            licensed_edges.append([0, l_idx])
            licensed_attr.append([1.0])

        # Self-loop similar edge keeps query node in relational channel.
        similar_edges.append([0, 0])
        similar_attr.append([1.0])

        result_records: list[tuple[str, float, dict[str, Any]]] = []
        for result in qdrant_results:
            neighbor_asset_id, similarity, metadata = self._metadata_from_result(result)
            if not neighbor_asset_id:
                continue
            result_records.append((neighbor_asset_id, similarity, metadata))

        if self.graph_db is not None:
            query_asset_id = str(query_metadata.get("asset_id", "__query__"))
            try:
                self.graph_db.upsert_asset_context(
                    asset_id=query_asset_id,
                    metadata={
                        **query_metadata,
                        "modality": query_metadata.get("modality", "image"),
                    },
                    neighbors=[
                        {
                            "asset_id": aid,
                            "similarity": sim,
                            "is_flagged": bool(meta.get("is_flagged", False)),
                            "modality": meta.get("modality"),
                            "flagged_weight": float(meta.get("flagged_weight", self.flagged_edge_boost)),
                        }
                        for aid, sim, meta in result_records
                    ],
                )
                neighborhood = self.graph_db.fetch_asset_neighborhood(asset_id=query_asset_id, limit_assets=64)
                neo_records: list[tuple[str, float, dict[str, Any]]] = []
                for n in neighborhood.get("neighbors", []):
                    n_asset_id = str(n.get("asset_id", ""))
                    if not n_asset_id:
                        continue
                    neo_records.append((n_asset_id, float(n.get("similarity", 0.0)), dict(n)))
                if neo_records:
                    result_records = neo_records
            except Exception:
                pass

        for neighbor_asset_id, similarity, metadata in result_records:
            n_idx = len(asset_ids)
            asset_ids.append(neighbor_asset_id)
            asset_features.append(self._safe_embedding(metadata, query_vec, similarity))

            sim_w = float(np.clip(similarity, 0.0, 1.0))
            similar_edges.append([0, n_idx])
            similar_attr.append([sim_w])

            if bool(metadata.get("is_flagged", False)):
                flagged_edges.append([0, n_idx])
                flagged_attr.append([self.flagged_edge_boost])

            creator_id = metadata.get("creator_id")
            if creator_id:
                c_idx = upsert_creator(
                    str(creator_id),
                    float(metadata.get("creator_trust_score", 0.5)),
                    float(metadata.get("creator_tenure_months", 12.0)),
                )
                created_edges.append([n_idx, c_idx])
                created_attr.append([0.3])

            licensee_id = metadata.get("licensee_id")
            if licensee_id:
                l_idx = upsert_licensee(
                    str(licensee_id),
                    float(metadata.get("license_status", 0.0)),
                )
                licensed_edges.append([n_idx, l_idx])
                licensed_attr.append([1.0])

        data = HeteroData()

        data["Asset"].x = torch.tensor(np.vstack(asset_features), dtype=torch.float32)
        data["Asset"].node_ids = asset_ids
        data["Asset"].query_index = torch.tensor([0], dtype=torch.long)

        if creator_features:
            data["Creator"].x = torch.tensor(np.asarray(creator_features, dtype=np.float32), dtype=torch.float32)
            data["Creator"].node_ids = creator_ids
        else:
            data["Creator"].x = torch.zeros((1, 2), dtype=torch.float32)
            data["Creator"].node_ids = ["__dummy_creator__"]

        if licensee_features:
            data["Licensee"].x = torch.tensor(np.asarray(licensee_features, dtype=np.float32), dtype=torch.float32)
            data["Licensee"].node_ids = licensee_ids
        else:
            data["Licensee"].x = torch.zeros((1, 1), dtype=torch.float32)
            data["Licensee"].node_ids = ["__dummy_licensee__"]

        if not created_edges:
            created_edges = [[0, 0]]
            created_attr = [[0.0]]
        if not licensed_edges:
            licensed_edges = [[0, 0]]
            licensed_attr = [[0.0]]
        if not flagged_edges:
            flagged_edges = [[0, 0]]
            flagged_attr = [[0.0]]

        data[("Asset", "created_by", "Creator")].edge_index = torch.tensor(created_edges, dtype=torch.long).t().contiguous()
        data[("Asset", "created_by", "Creator")].edge_attr = torch.tensor(created_attr, dtype=torch.float32)

        data[("Asset", "licensed_to", "Licensee")].edge_index = torch.tensor(licensed_edges, dtype=torch.long).t().contiguous()
        data[("Asset", "licensed_to", "Licensee")].edge_attr = torch.tensor(licensed_attr, dtype=torch.float32)

        data[("Asset", "similar_to", "Asset")].edge_index = torch.tensor(similar_edges, dtype=torch.long).t().contiguous()
        data[("Asset", "similar_to", "Asset")].edge_attr = torch.tensor(similar_attr, dtype=torch.float32)

        data[("Asset", "flagged_with", "Asset")].edge_index = torch.tensor(flagged_edges, dtype=torch.long).t().contiguous()
        data[("Asset", "flagged_with", "Asset")].edge_attr = torch.tensor(flagged_attr, dtype=torch.float32)

        # Add reverse relations so `Asset` nodes can receive creator/licensee signals.
        data = self._to_undirected(data)
        return data

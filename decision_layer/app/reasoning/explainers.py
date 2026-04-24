from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import shap
import torch
import torch.nn.functional as F
from captum.attr import IntegratedGradients
from torch_geometric.data import HeteroData


@dataclass
class VisualRegion:
    x: int
    y: int
    width: int
    height: int
    importance: float


class VisualExplainer:
    """Captum Integrated Gradients explainer for Stage-2 visual embedding."""

    def __init__(self, semantic_embedder: Any) -> None:
        self.device = torch.device("cpu")
        self.feature_extractor = semantic_embedder.feature_extractor
        self.projection = semantic_embedder.projection
        self.transform = semantic_embedder.transform

        self.feature_extractor.eval()
        self.projection.eval()

        def _forward_score(x: torch.Tensor) -> torch.Tensor:
            features = self.feature_extractor(x).flatten(1)
            projected = self.projection(features)
            # Scalar objective for attribution on embedding stage.
            return torch.sum(torch.abs(projected), dim=1)

        self._ig = IntegratedGradients(_forward_score)

    def get_visual_explanation(self, image_tensor: torch.Tensor) -> np.ndarray:
        """Returns a normalized 224x224 heatmap."""
        if image_tensor.ndim == 3:
            image_tensor = image_tensor.unsqueeze(0)

        image_tensor = image_tensor.to(self.device)
        baseline = torch.zeros_like(image_tensor)

        attributions = self._ig.attribute(
            image_tensor,
            baselines=baseline,
            n_steps=16,
        )
        # Channel-reduced saliency map.
        heatmap = attributions.abs().sum(dim=1).squeeze(0).detach().cpu().numpy()

        heatmap -= heatmap.min()
        max_val = float(heatmap.max())
        if max_val > 1e-8:
            heatmap /= max_val

        return heatmap.astype(np.float32)

    @staticmethod
    def heatmap_to_bounding_boxes(heatmap: np.ndarray, top_k: int = 3) -> list[dict[str, Any]]:
        if heatmap.ndim != 2:
            raise ValueError("Heatmap must be a 2D array")

        h, w = heatmap.shape
        img = np.clip(heatmap * 255.0, 0, 255).astype(np.uint8)

        # Adaptive threshold to isolate most influential regions.
        threshold = int(np.percentile(img, 90))
        _, mask = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)

        # Clean up small noise with morphology.
        kernel = np.ones((5, 5), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions: list[VisualRegion] = []
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            if bw * bh < 64:
                continue
            patch = heatmap[y : y + bh, x : x + bw]
            importance = float(patch.mean() * patch.size)
            regions.append(VisualRegion(x=x, y=y, width=bw, height=bh, importance=importance))

        regions.sort(key=lambda r: r.importance, reverse=True)

        top = regions[:top_k]
        if not top:
            # Fallback central box when attribution is diffuse.
            return [{"x": w // 4, "y": h // 4, "width": w // 2, "height": h // 2, "importance": 0.0}]

        return [r.__dict__ for r in top]


class GraphExplainer:
    """SHAP KernelExplainer wrapper treating RightsGNN as a black box."""

    _FEATURES_FULL = [
        "creator_verified",
        "creator_tenure",
        "license_active",
        "flagged_density",
        "similarity_strength",
        "neighbor_count_norm",
        "creator_count_norm",
        "licensee_count_norm",
        "max_similarity",
    ]

    def __init__(self, rights_model: torch.nn.Module, max_feature_sample: int = 6) -> None:
        self.model = rights_model
        self.model.eval()
        self.device = torch.device("cpu")
        self.max_feature_sample = max_feature_sample

    @staticmethod
    def _safe_mean(x: torch.Tensor, col: int) -> float:
        if x.numel() == 0:
            return 0.0
        return float(x[:, col].mean().item())

    def _extract_feature_vector(self, data: HeteroData) -> dict[str, float]:
        creator_x = data["Creator"].x
        licensee_x = data["Licensee"].x
        similar_attr = data[("Asset", "similar_to", "Asset")].edge_attr
        flagged_attr = data[("Asset", "flagged_with", "Asset")].edge_attr

        n_assets = int(data["Asset"].x.shape[0])
        n_creators = int(creator_x.shape[0])
        n_licensees = int(licensee_x.shape[0])

        similar_mean = float(similar_attr.mean().item()) if similar_attr.numel() else 0.0
        similar_max = float(similar_attr.max().item()) if similar_attr.numel() else 0.0
        flagged_mean = float(flagged_attr.mean().item()) if flagged_attr.numel() else 0.0

        return {
            "creator_verified": self._safe_mean(creator_x, 0),
            "creator_tenure": self._safe_mean(creator_x, 1),
            "license_active": self._safe_mean(licensee_x, 0),
            "flagged_density": float(np.clip(flagged_mean, 0.0, 2.0)),
            "similarity_strength": float(np.clip(similar_mean, 0.0, 1.0)),
            "neighbor_count_norm": float(np.clip((n_assets - 1) / 64.0, 0.0, 1.0)),
            "creator_count_norm": float(np.clip(n_creators / 32.0, 0.0, 1.0)),
            "licensee_count_norm": float(np.clip(n_licensees / 32.0, 0.0, 1.0)),
            "max_similarity": float(np.clip(similar_max, 0.0, 1.0)),
        }

    def _selected_features(self, data: HeteroData) -> list[str]:
        # Latency optimization: if graph is large, explain a sampled subset of features.
        n_assets = int(data["Asset"].x.shape[0])
        if n_assets > 64:
            return self._FEATURES_FULL[: self.max_feature_sample]
        return self._FEATURES_FULL

    def _vector_to_graph(self, base_data: HeteroData, feature_names: list[str], x: np.ndarray) -> HeteroData:
        data = deepcopy(base_data)
        vals = {name: float(v) for name, v in zip(feature_names, x, strict=False)}

        if "creator_verified" in vals:
            data["Creator"].x[:, 0] = vals["creator_verified"]
        if "creator_tenure" in vals:
            data["Creator"].x[:, 1] = vals["creator_tenure"]
        if "license_active" in vals:
            data["Licensee"].x[:, 0] = vals["license_active"]

        if "flagged_density" in vals:
            e = data[("Asset", "flagged_with", "Asset")].edge_attr
            if e.numel():
                e[:] = vals["flagged_density"]

        if "similarity_strength" in vals:
            e = data[("Asset", "similar_to", "Asset")].edge_attr
            if e.numel():
                e[:] = vals["similarity_strength"]

        if "max_similarity" in vals:
            e = data[("Asset", "similar_to", "Asset")].edge_attr
            if e.numel():
                e[0, 0] = vals["max_similarity"]

        # Count-based features are approximated by masking feature rows (cheap CPU path).
        if "creator_count_norm" in vals:
            max_keep = max(1, int(round(vals["creator_count_norm"] * data["Creator"].x.shape[0])))
            if max_keep < data["Creator"].x.shape[0]:
                data["Creator"].x[max_keep:, :] = 0.0

        if "licensee_count_norm" in vals:
            max_keep = max(1, int(round(vals["licensee_count_norm"] * data["Licensee"].x.shape[0])))
            if max_keep < data["Licensee"].x.shape[0]:
                data["Licensee"].x[max_keep:, :] = 0.0

        if "neighbor_count_norm" in vals:
            keep_neighbors = max(1, int(round(vals["neighbor_count_norm"] * max(1, data["Asset"].x.shape[0] - 1))))
            e_idx = data[("Asset", "similar_to", "Asset")].edge_index
            e_attr = data[("Asset", "similar_to", "Asset")].edge_attr
            if e_idx.shape[1] > 1:
                query_mask = e_idx[0] == 0
                query_edges = torch.where(query_mask)[0]
                # Keep self-loop + first K query edges.
                max_keep_edges = min(len(query_edges), keep_neighbors + 1)
                keep_idx = query_edges[:max_keep_edges]
                drop_idx = query_edges[max_keep_edges:]
                if len(drop_idx) > 0:
                    e_attr[drop_idx, :] = 0.0

        return data

    @torch.no_grad()
    def _predict_infringement_prob(self, data: HeteroData) -> float:
        x_dict = {k: v.x.to(self.device) for k, v in data.node_items()}
        edge_index_dict = {k: v.edge_index.to(self.device) for k, v in data.edge_items()}

        infringement_logit, _, _ = self.model(
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            query_asset_index=0,
        )
        return float(torch.sigmoid(infringement_logit).item())

    def get_graph_explanation(self, subgraph_data: HeteroData) -> list[dict[str, Any]]:
        feature_map = self._extract_feature_vector(subgraph_data)
        feature_names = self._selected_features(subgraph_data)

        x0 = np.array([feature_map[name] for name in feature_names], dtype=np.float32)
        background = np.vstack([x0, np.zeros_like(x0)])

        def _black_box_predict(samples: np.ndarray) -> np.ndarray:
            samples = np.asarray(samples, dtype=np.float32)
            out: list[float] = []
            for row in samples:
                perturbed = self._vector_to_graph(subgraph_data, feature_names, row)
                out.append(self._predict_infringement_prob(perturbed))
            return np.asarray(out, dtype=np.float32)

        explainer = shap.KernelExplainer(_black_box_predict, background)
        nsamples = min(64, max(20, len(feature_names) * 6))
        shap_values = explainer.shap_values(x0.reshape(1, -1), nsamples=nsamples)

        if isinstance(shap_values, list):
            values = np.asarray(shap_values[0], dtype=np.float32).reshape(-1)
        else:
            values = np.asarray(shap_values, dtype=np.float32).reshape(-1)

        pairs = sorted(
            zip(feature_names, values.tolist(), strict=False),
            key=lambda p: abs(p[1]),
            reverse=True,
        )

        top = pairs[:5]
        return [{"factor": name, "shap_value": float(val)} for name, val in top]

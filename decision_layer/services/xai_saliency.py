from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class PopulationSaliencyWorker:
    """Worker that aggregates saliency maps by content category and produces average heatmap overlay."""

    def __init__(self, sample_size: int = 50, heatmap_shape: tuple[int, int] = (224, 224)) -> None:
        """Initialize saliency aggregation worker.

        Args:
            sample_size: Maximum number of saliency maps to aggregate per category.
            heatmap_shape: Output heatmap dimensions (height, width).
        """
        self.sample_size = sample_size
        self.heatmap_shape = heatmap_shape

    async def aggregate_saliency_maps(
        self,
        saliency_maps: list[dict[str, Any]],
        category: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate saliency maps and produce normalized average heatmap.

        Args:
            saliency_maps: List of saliency map dicts, each with 'data' (2D array-like).
            category: Optional category label for the aggregation result.

        Returns:
            Dict with average_heatmap, count, normalization_stats, and category.
        """

        if not saliency_maps:
            raise ValueError("No saliency maps provided")

        normalized_maps: list[np.ndarray] = []

        for smap in saliency_maps:
            if not isinstance(smap, dict):
                continue

            data = smap.get("data")
            if data is None:
                continue

            try:
                arr = np.asarray(data, dtype=np.float32)

                if arr.ndim != 2:
                    arr = arr.reshape(self.heatmap_shape)
                elif arr.shape != self.heatmap_shape:
                    arr = self._resize_map(arr, self.heatmap_shape)

                arr_min = np.min(arr)
                arr_max = np.max(arr)
                if arr_max > arr_min:
                    normalized = (arr - arr_min) / (arr_max - arr_min)
                else:
                    normalized = arr * 0.0

                normalized_maps.append(normalized)

                if len(normalized_maps) >= self.sample_size:
                    break
            except Exception as e:
                logger.warning(f"Failed to process saliency map: {e}")
                continue

        if not normalized_maps:
            raise ValueError("No valid saliency maps to aggregate")

        average_heatmap = np.mean(normalized_maps, axis=0).astype(np.float32)

        std_heatmap = np.std(normalized_maps, axis=0).astype(np.float32)

        return {
            "average_heatmap": average_heatmap.tolist(),
            "standard_deviation": std_heatmap.tolist(),
            "count": len(normalized_maps),
            "shape": list(self.heatmap_shape),
            "category": category or "unknown",
            "min_value": float(np.min(average_heatmap)),
            "max_value": float(np.max(average_heatmap)),
            "mean_intensity": float(np.mean(average_heatmap)),
        }

    async def aggregate_batch_by_category(
        self,
        saliency_records: list[dict[str, Any]],
        category_field: str = "content_type",
    ) -> dict[str, dict[str, Any]]:
        """Group saliency maps by category and aggregate each group.

        Args:
            saliency_records: List of records with saliency_map and category field.
            category_field: Field name to group by (e.g., 'content_type', 'modality').

        Returns:
            Dict mapping category -> aggregation result.
        """

        grouped: dict[str, list[dict[str, Any]]] = {}

        for record in saliency_records:
            if not isinstance(record, dict):
                continue

            category = str(record.get(category_field, "unknown"))
            saliency_map = record.get("saliency_map")

            if saliency_map is None:
                continue

            if category not in grouped:
                grouped[category] = []

            grouped[category].append({"data": saliency_map})

        results: dict[str, dict[str, Any]] = {}

        for category, maps in grouped.items():
            try:
                aggregated = await self.aggregate_saliency_maps(
                    saliency_maps=maps,
                    category=category,
                )
                results[category] = aggregated
            except Exception as e:
                logger.error(f"Failed to aggregate category '{category}': {e}")
                continue

        return results

    @staticmethod
    def _resize_map(arr: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
        """Simple bilinear resize for saliency maps."""
        try:
            import cv2

            return cv2.resize(arr, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_LINEAR)
        except ImportError:
            original_h, original_w = arr.shape
            target_h, target_w = target_shape

            scale_h = target_h / original_h
            scale_w = target_w / original_w

            y_indices = (np.arange(target_h) / scale_h).astype(int)
            x_indices = (np.arange(target_w) / scale_w).astype(int)

            y_indices = np.clip(y_indices, 0, original_h - 1)
            x_indices = np.clip(x_indices, 0, original_w - 1)

            resized = arr[np.ix_(y_indices, x_indices)]
            return resized


__all__ = [
    "PopulationSaliencyWorker",
]

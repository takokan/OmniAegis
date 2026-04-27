from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import ks_2samp


@dataclass(frozen=True)
class DriftDetectionResult:
    """Result of a drift detection test for a single feature."""

    feature_name: str
    current_mean: float
    reference_mean: float
    current_std: float
    reference_std: float
    ks_statistic: float
    p_value: float
    is_drifted: bool
    notes: str = ""


class DriftDetectorError(RuntimeError):
    """Raised when drift detection operations fail."""


class KSDriftDetector:
    """Kolmogorov-Smirnov test for SHAP value distribution drift detection."""

    def __init__(self, p_threshold: float = 0.05) -> None:
        """Initialize detector with significance threshold.

        Args:
            p_threshold: P-value threshold for drift flagging (default 0.05).
        """
        if not 0.0 < p_threshold < 1.0:
            raise ValueError("p_threshold must be in (0, 1)")
        self.p_threshold = p_threshold

    def detect_drift(
        self,
        current_values: list[float] | np.ndarray,
        reference_values: list[float] | np.ndarray,
        feature_name: str = "unknown",
    ) -> DriftDetectionResult:
        """Perform KS test between current and reference distributions.

        Args:
            current_values: Feature values from current period (e.g., this week).
            reference_values: Feature values from reference period (e.g., last 30 days).
            feature_name: Human-readable feature identifier.

        Returns:
            DriftDetectionResult with KS statistic, p-value, and drift flag.
        """

        try:
            current = np.asarray(current_values, dtype=np.float64)
            reference = np.asarray(reference_values, dtype=np.float64)
        except (ValueError, TypeError) as exc:
            raise DriftDetectorError(f"Failed to convert values to numpy arrays: {exc}") from exc

        if current.size == 0 or reference.size == 0:
            raise DriftDetectorError("Cannot perform KS test on empty distributions")

        current_mean = float(np.mean(current))
        current_std = float(np.std(current))
        reference_mean = float(np.mean(reference))
        reference_std = float(np.std(reference))

        try:
            ks_stat, p_val = ks_2samp(current, reference)
        except Exception as exc:
            raise DriftDetectorError(f"KS test failed: {exc}") from exc

        is_drifted = p_val < self.p_threshold

        notes = ""
        if is_drifted:
            delta_mean = abs(current_mean - reference_mean)
            notes = f"Distribution shifted: mean {current_mean:.4f} vs {reference_mean:.4f} (Δ={delta_mean:.4f})"

        return DriftDetectionResult(
            feature_name=feature_name,
            current_mean=current_mean,
            reference_mean=reference_mean,
            current_std=current_std,
            reference_std=reference_std,
            ks_statistic=float(ks_stat),
            p_value=float(p_val),
            is_drifted=is_drifted,
            notes=notes,
        )

    def detect_drift_batch(
        self,
        current_features: dict[str, list[float]],
        reference_features: dict[str, list[float]],
    ) -> list[DriftDetectionResult]:
        """Perform KS test on multiple features simultaneously.

        Args:
            current_features: Dict mapping feature names to current-period values.
            reference_features: Dict mapping feature names to reference-period values.

        Returns:
            List of DriftDetectionResult objects, one per feature.
        """

        common_features = set(current_features.keys()) & set(reference_features.keys())
        if not common_features:
            raise DriftDetectorError("No common features between current and reference")

        results: list[DriftDetectionResult] = []
        for feature_name in sorted(common_features):
            try:
                result = self.detect_drift(
                    current_values=current_features[feature_name],
                    reference_values=reference_features[feature_name],
                    feature_name=feature_name,
                )
                results.append(result)
            except DriftDetectorError:
                continue

        return results

    @staticmethod
    def filter_drifted_features(results: list[DriftDetectionResult]) -> list[DriftDetectionResult]:
        """Filter results to only drifted features."""
        return [r for r in results if r.is_drifted]


__all__ = [
    "DriftDetectionResult",
    "DriftDetectorError",
    "KSDriftDetector",
]

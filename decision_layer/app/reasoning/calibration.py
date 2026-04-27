from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


class TemperatureScaler(nn.Module):
    """Single-parameter temperature scaling for binary logits calibration."""

    def __init__(self, init_temperature: float = 1.0) -> None:
        super().__init__()
        self.temperature = nn.Parameter(torch.tensor(float(init_temperature), dtype=torch.float32))

    def forward(self, logits: torch.Tensor) -> torch.Tensor:
        # Keep temperature positive and numerically stable.
        temp = torch.clamp(self.temperature, min=1e-3)
        return torch.sigmoid(logits / temp)


def compute_ece(preds: np.ndarray | list[float], targets: np.ndarray | list[int], n_bins: int = 10) -> float:
    """Expected Calibration Error for binary predictions.

    Args:
        preds: predicted probabilities in [0, 1].
        targets: binary ground-truth labels {0, 1}.
        n_bins: number of equal-width confidence bins.
    """
    p = np.asarray(preds, dtype=np.float32).reshape(-1)
    y = np.asarray(targets, dtype=np.int64).reshape(-1)

    if p.size == 0:
        return 0.0
    if p.size != y.size:
        raise ValueError("preds and targets must have the same length")
    if n_bins <= 0:
        raise ValueError("n_bins must be > 0")

    p = np.clip(p, 0.0, 1.0)
    y_hat = (p >= 0.5).astype(np.int64)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1, dtype=np.float32)
    ece = 0.0

    for i in range(n_bins):
        left = bin_edges[i]
        right = bin_edges[i + 1]

        if i == n_bins - 1:
            mask = (p >= left) & (p <= right)
        else:
            mask = (p >= left) & (p < right)

        count = int(mask.sum())
        if count == 0:
            continue

        avg_conf = float(p[mask].mean())
        avg_acc = float((y_hat[mask] == y[mask]).mean())
        weight = count / float(p.size)
        ece += weight * abs(avg_acc - avg_conf)

    return float(ece)

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

import torch
import torch.nn.functional as F
from opacus import PrivacyEngine
from prometheus_client import Gauge
from torch import nn
from torch.optim import Optimizer
from torch.utils.data import DataLoader


@dataclass(frozen=True)
class DPConfig:
    """Differential privacy configuration for edge-side local training."""

    max_grad_norm: float = 1.0
    target_epsilon: float = 1.0
    target_delta: float = 1e-5
    epochs: int = 3


class DPTrainerError(RuntimeError):
    """Raised when Opacus wrapping/training cannot be completed safely."""


class DPTrainer:
    """Opacus-aware trainer encapsulating private training and epsilon accounting."""

    def __init__(self, config: DPConfig | None = None) -> None:
        env_config = DPConfig(
            max_grad_norm=float(os.getenv("DP_MAX_GRAD_NORM", "1.0")),
            target_epsilon=float(os.getenv("DP_TARGET_EPSILON", "1.0")),
            target_delta=float(os.getenv("DP_TARGET_DELTA", "1e-5")),
            epochs=int(os.getenv("DP_LOCAL_EPOCHS", "3")),
        )
        self.config = config or env_config
        self.privacy_engine: PrivacyEngine | None = None
        self.privacy_budget_remaining = Gauge(
            "privacy_budget_remaining",
            "Fraction of DP budget remaining on this edge runtime",
            labelnames=("node_id",),
        )

    def make_private_with_epsilon(
        self,
        model: nn.Module,
        optimizer: Optimizer,
        data_loader: DataLoader,
    ) -> tuple[nn.Module, Optimizer, DataLoader]:
        """Wrap model/optimizer/loader with Opacus using epsilon targeting."""
        self.privacy_engine = PrivacyEngine(secure_mode=False)
        try:
            return self.privacy_engine.make_private_with_epsilon(
                module=model,
                optimizer=optimizer,
                data_loader=data_loader,
                target_epsilon=self.config.target_epsilon,
                target_delta=self.config.target_delta,
                epochs=self.config.epochs,
                max_grad_norm=self.config.max_grad_norm,
            )
        except Exception as exc:
            raise DPTrainerError(f"Opacus could not privatize the model: {exc}") from exc

    def epsilon_spent(self) -> float:
        """Return epsilon consumed so far by current `PrivacyEngine`."""
        if self.privacy_engine is None:
            return 0.0
        accountant = getattr(self.privacy_engine, "accountant", None)
        if accountant is None:
            return 0.0
        return float(accountant.get_epsilon(delta=self.config.target_delta))

    def publish_budget(self, node_id: str) -> float:
        """Update the local Prometheus gauge and return remaining budget fraction."""
        eps = self.epsilon_spent()
        remaining = max(0.0, 1.0 - (eps / max(self.config.target_epsilon, 1e-12)))
        self.privacy_budget_remaining.labels(node_id=node_id).set(remaining)
        return remaining

    def train_private_epochs(
        self,
        model: nn.Module,
        optimizer: Optimizer,
        data_loader: DataLoader,
        device: torch.device,
    ) -> tuple[float, float]:
        """Run private local training and return `(mean_loss, epsilon_spent)`.

        Dataset contract: each batch must provide `(features, labels)` where labels
        are binary (`0`/`1`) for BCE-with-logits optimization.
        """
        model, optimizer, data_loader = self.make_private_with_epsilon(model, optimizer, data_loader)
        model.to(device)

        losses: list[float] = []
        for _ in range(self.config.epochs):
            model.train()
            for batch in data_loader:
                if not isinstance(batch, (list, tuple)) or len(batch) < 2:
                    raise DPTrainerError("Expected batch to contain `(features, labels)` tensors")

                features = batch[0].to(device)
                labels = batch[1].to(device).float().view(-1, 1)

                optimizer.zero_grad(set_to_none=True)
                logits = model(features)
                loss = F.binary_cross_entropy_with_logits(logits, labels)
                loss.backward()
                optimizer.step()

                losses.append(float(loss.item()))

        avg_loss = float(sum(losses) / len(losses)) if losses else 0.0
        eps = self.epsilon_spent()
        return avg_loss, eps

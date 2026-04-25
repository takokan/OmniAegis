from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import flwr as fl
import numpy as np
import redis  # type: ignore[reportMissingImports]
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

try:
    from decision_layer.services.fl_edge.dp_trainer import DPConfig, DPTrainer  # type: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    from services.fl_edge.dp_trainer import DPConfig, DPTrainer  # type: ignore[reportMissingImports]


class SentinelGNN(nn.Module):
    """Resource-friendly surrogate for Sentinel federated training.

    This model keeps the FL/DP plumbing lightweight for single-node simulation,
    while preserving a clean extension point to swap in the full graph model.
    """

    def __init__(self, in_features: int = 32, hidden_dim: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_features, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        return self.net(x)


@dataclass(frozen=True)
class ClientConfig:
    """Config contract for FL edge client simulation."""

    node_id: str
    in_features: int = 32
    batch_size: int = 8
    lr: float = 1e-3
    redis_url: str = "redis://localhost:6379/0"


class SentinelNumPyClient(fl.client.NumPyClient):
    """Flower NumPyClient with Opacus private local training loop."""

    def __init__(self, config: ClientConfig, shard_samples: list[dict[str, Any]]) -> None:
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SentinelGNN(in_features=config.in_features)
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=config.lr)
        self.dp_trainer = DPTrainer(DPConfig(max_grad_norm=1.0, target_epsilon=1.0, target_delta=1e-5, epochs=3))
        self.redis = redis.Redis.from_url(config.redis_url, decode_responses=True)

        features, labels = self._build_tensor_dataset(shard_samples, in_features=config.in_features)
        dataset = TensorDataset(features, labels)
        self.train_loader = DataLoader(dataset, batch_size=config.batch_size, shuffle=True, drop_last=False)

    @staticmethod
    def _build_tensor_dataset(samples: list[dict[str, Any]], in_features: int) -> tuple[torch.Tensor, torch.Tensor]:
        if not samples:
            x = torch.zeros((1, in_features), dtype=torch.float32)
            y = torch.zeros((1, 1), dtype=torch.float32)
            return x, y

        x_rows: list[np.ndarray] = []
        y_rows: list[float] = []
        for sample in samples:
            raw_vec = sample.get("features")
            raw_label = sample.get("label", 0)
            if raw_vec is None:
                vec = np.zeros((in_features,), dtype=np.float32)
            else:
                vec = np.asarray(raw_vec, dtype=np.float32).reshape(-1)
                if vec.size < in_features:
                    pad = np.zeros((in_features - vec.size,), dtype=np.float32)
                    vec = np.concatenate([vec, pad], axis=0)
                elif vec.size > in_features:
                    vec = vec[:in_features]
            x_rows.append(vec)
            y_rows.append(float(1.0 if raw_label else 0.0))

        x = torch.from_numpy(np.vstack(x_rows).astype(np.float32))
        y = torch.tensor(y_rows, dtype=torch.float32).view(-1, 1)
        return x, y

    def get_parameters(self, config: dict[str, Any]) -> list[np.ndarray]:
        return [p.detach().cpu().numpy() for p in self.model.state_dict().values()]

    def set_parameters(self, parameters: list[np.ndarray]) -> None:
        state_dict = self.model.state_dict()
        if len(parameters) != len(state_dict):
            raise ValueError(f"Parameter length mismatch: got {len(parameters)}, expected {len(state_dict)}")

        new_state = {}
        for key, arr in zip(state_dict.keys(), parameters, strict=False):
            new_state[key] = torch.tensor(arr, dtype=state_dict[key].dtype)
        self.model.load_state_dict(new_state, strict=True)

    def fit(self, parameters: list[np.ndarray], config: dict[str, Any]) -> tuple[list[np.ndarray], int, dict[str, Any]]:
        self.set_parameters(parameters)
        self.model.to(self.device)

        avg_loss, epsilon_spent = self.dp_trainer.train_private_epochs(
            model=self.model,
            optimizer=self.optimizer,
            data_loader=self.train_loader,
            device=self.device,
        )

        remaining = self.dp_trainer.publish_budget(node_id=self.config.node_id)
        self.redis.set(f"fl:node:{self.config.node_id}:epsilon", f"{epsilon_spent:.8f}", ex=3600)
        self.redis.publish(
            "fl:privacy_budget",
            json.dumps({"node_id": self.config.node_id, "epsilon": epsilon_spent, "remaining": remaining}),
        )

        return self.get_parameters(config={}), len(self.train_loader.dataset), {
            "train_loss": avg_loss,
            "epsilon": float(epsilon_spent),
        }

    def evaluate(self, parameters: list[np.ndarray], config: dict[str, Any]) -> tuple[float, int, dict[str, Any]]:
        self.set_parameters(parameters)
        self.model.to(self.device)
        self.model.eval()

        loss_total = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for batch in self.train_loader:
                features = batch[0].to(self.device)
                labels = batch[1].to(self.device)
                logits = self.model(features)
                loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)
                loss_total += float(loss.item()) * labels.shape[0]

                preds = (torch.sigmoid(logits) >= 0.5).float()
                correct += int((preds == labels).sum().item())
                total += int(labels.shape[0])

        avg_loss = (loss_total / float(total)) if total > 0 else 0.0
        accuracy = (correct / float(total)) if total > 0 else 0.0
        return avg_loss, total, {"accuracy": accuracy}


def client_factory(node_id: str, shard_samples: list[dict[str, Any]]) -> SentinelNumPyClient:
    cfg = ClientConfig(
        node_id=node_id,
        in_features=int(os.getenv("FL_IN_FEATURES", "32")),
        batch_size=int(os.getenv("FL_BATCH_SIZE", "8")),
        lr=float(os.getenv("FL_CLIENT_LR", "1e-3")),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
    return SentinelNumPyClient(config=cfg, shard_samples=shard_samples)

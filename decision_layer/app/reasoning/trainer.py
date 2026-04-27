from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.data import HeteroData


@dataclass
class TrainMetrics:
    loss: float
    loss_infringement: float
    loss_attribution: float


class RightsGNNTrainer:
    """Trainer for Stage-5 model.

    Weighted objective:
    - 0.7 * BCEWithLogits (infringement)
    - 0.3 * CrossEntropy (creator attribution)

    Includes gradient clipping at norm=1.0.
    """

    def __init__(self, model: nn.Module, lr: float = 1e-3, weight_decay: float = 1e-4) -> None:
        self.model = model
        self.optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    @staticmethod
    def _extract_labels(data: HeteroData) -> tuple[torch.Tensor, torch.Tensor]:
        if not hasattr(data["Asset"], "y_infringing"):
            raise ValueError("Missing `Asset.y_infringing` label tensor")
        if not hasattr(data["Asset"], "y_creator_index"):
            raise ValueError("Missing `Asset.y_creator_index` label tensor")

        y_infringing = data["Asset"].y_infringing[0].float().view(())
        y_creator_index = data["Asset"].y_creator_index[0].long().view(())
        return y_infringing, y_creator_index

    def train_step(self, data: HeteroData) -> TrainMetrics:
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)

        x_dict = {k: v.x for k, v in data.node_items()}
        edge_index_dict = {k: v.edge_index for k, v in data.edge_items()}

        infringement_logit, attribution_logits, _ = self.model(
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            query_asset_index=0,
        )

        y_infringing, y_creator_index = self._extract_labels(data)

        loss_infringement = F.binary_cross_entropy_with_logits(
            infringement_logit.view(1),
            y_infringing.view(1),
        )
        loss_attribution = F.cross_entropy(
            attribution_logits.view(1, -1),
            y_creator_index.view(1),
        )

        loss = 0.7 * loss_infringement + 0.3 * loss_attribution
        loss.backward()

        nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        self.optimizer.step()

        return TrainMetrics(
            loss=float(loss.item()),
            loss_infringement=float(loss_infringement.item()),
            loss_attribution=float(loss_attribution.item()),
        )

    def train_epoch(self, dataset: Iterable[HeteroData]) -> TrainMetrics:
        losses: list[float] = []
        loss_inf: list[float] = []
        loss_attr: list[float] = []

        for data in dataset:
            metrics = self.train_step(data)
            losses.append(metrics.loss)
            loss_inf.append(metrics.loss_infringement)
            loss_attr.append(metrics.loss_attribution)

        if not losses:
            raise ValueError("Empty dataset provided to train_epoch")

        return TrainMetrics(
            loss=sum(losses) / len(losses),
            loss_infringement=sum(loss_inf) / len(loss_inf),
            loss_attribution=sum(loss_attr) / len(loss_attr),
        )

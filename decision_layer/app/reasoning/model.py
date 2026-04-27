from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import HeteroData
from torch_geometric.nn import HeteroConv, SAGEConv


class RightsGNN(nn.Module):
    """Stage-5 Reasoning Engine (2-hop GraphSAGE on hetero graph).

    - Node projections: each node type -> shared 256-d space.
    - Two SAGEConv hops: 256 -> 256 -> 128.
    - Dual heads:
      1) Infringement head: binary logit.
      2) Attribution head: dynamic N logits for creator candidates in subgraph.

    Contract: query `Asset` node must be index 0.
    """

    def __init__(self, hidden_dim: int = 256, out_dim: int = 128, dropout: float = 0.1) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.out_dim = out_dim
        self.dropout = dropout

        self.asset_proj = nn.Linear(512, hidden_dim)
        self.creator_proj = nn.Linear(2, hidden_dim)
        self.licensee_proj = nn.Linear(1, hidden_dim)

        relations = [
            ("Asset", "created_by", "Creator"),
            ("Asset", "licensed_to", "Licensee"),
            ("Asset", "similar_to", "Asset"),
            ("Asset", "flagged_with", "Asset"),
            ("Creator", "rev_created_by", "Asset"),
            ("Licensee", "rev_licensed_to", "Asset"),
        ]

        self.conv1 = HeteroConv(
            {
                rel: SAGEConv((-1, -1), hidden_dim, aggr="mean")
                for rel in relations
            },
            aggr="sum",
        )
        self.conv2 = HeteroConv(
            {
                rel: SAGEConv((-1, -1), out_dim, aggr="mean")
                for rel in relations
            },
            aggr="sum",
        )

        self.infringement_head = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(out_dim, 1),
        )

        # Scores each creator candidate using query asset context.
        self.attribution_head = nn.Sequential(
            nn.Linear(out_dim * 2, out_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(out_dim, 1),
        )

    def _project_inputs(self, x_dict: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        out: dict[str, torch.Tensor] = {}
        out["Asset"] = self.asset_proj(x_dict["Asset"])
        out["Creator"] = self.creator_proj(x_dict["Creator"])
        out["Licensee"] = self.licensee_proj(x_dict["Licensee"])
        return out

    def encode(
        self,
        x_dict: dict[str, torch.Tensor],
        edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
    ) -> dict[str, torch.Tensor]:
        h = self._project_inputs(x_dict)
        h = self.conv1(h, edge_index_dict)
        h = {k: F.relu(v) for k, v in h.items()}
        h = {k: F.dropout(v, p=self.dropout, training=self.training) for k, v in h.items()}

        h = self.conv2(h, edge_index_dict)
        h = {k: F.relu(v) for k, v in h.items()}
        return h

    def forward(
        self,
        x_dict: dict[str, torch.Tensor],
        edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
        query_asset_index: int = 0,
    ) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:
        h = self.encode(x_dict=x_dict, edge_index_dict=edge_index_dict)

        query_asset = h["Asset"][query_asset_index]  # (128,)

        # Binary infringement logit.
        infringement_logit = self.infringement_head(query_asset).view(())

        # Dynamic creator attribution logits, one per creator node (N creators).
        creator_repr = h["Creator"]  # (N, 128)
        q_expand = query_asset.unsqueeze(0).expand(creator_repr.size(0), -1)
        pair_repr = torch.cat([q_expand, creator_repr], dim=-1)
        attribution_logits = self.attribution_head(pair_repr).squeeze(-1)  # (N,)

        return infringement_logit, attribution_logits, h

    def forward_heterodata(self, data: HeteroData) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:
        x_dict = {k: v.x for k, v in data.node_items()}
        edge_index_dict = {k: v.edge_index for k, v in data.edge_items()}
        return self.forward(x_dict=x_dict, edge_index_dict=edge_index_dict, query_asset_index=0)

    @staticmethod
    def prediction_dict(
        infringement_logit: torch.Tensor,
        attribution_logits: torch.Tensor,
    ) -> dict[str, Any]:
        p_infringing = torch.sigmoid(infringement_logit)
        creator_dist = torch.softmax(attribution_logits, dim=0)
        return {
            "infringement_probability": float(p_infringing.item()),
            "creator_distribution": creator_dist.detach().cpu().tolist(),
        }

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

try:  # optional dependency in some runtimes
    from torch_geometric.nn import GATv2Conv, HeteroConv
    _TORCH_GEOMETRIC_AVAILABLE = True
except Exception:  # pragma: no cover
    GATv2Conv = None  # type: ignore[assignment]
    HeteroConv = None  # type: ignore[assignment]
    _TORCH_GEOMETRIC_AVAILABLE = False


class HeteroGATReasoner(nn.Module):
    """Heterogeneous GATv2 reasoner for final policy decision.

    Output classes:
    - 0: Innocent
    - 1: Authorized
    - 2: Infringing

    Design note:
    Relation-specific convolutions let the model learn different propagation
    behavior for `licensed_to` vs `flagged_with` signals.
    """

    def __init__(
        self,
        hidden_dim: int = 128,
        out_classes: int = 3,
        heads: int = 2,
        dropout: float = 0.1,
    ) -> None:
        if not _TORCH_GEOMETRIC_AVAILABLE or GATv2Conv is None or HeteroConv is None:
            raise RuntimeError(
                "torch_geometric is unavailable in this runtime. Install `torch-geometric` in the same environment as the backend process."
            )
        super().__init__()
        self.hidden_dim = hidden_dim
        self.dropout = dropout

        # Per-node-type input projections.
        self.asset_proj = nn.Linear(512, hidden_dim)
        self.creator_proj = nn.Linear(2, hidden_dim)
        self.licensee_proj = nn.Linear(1, hidden_dim)

        self.conv1 = HeteroConv(
            {
                ("Asset", "created_by", "Creator"): GATv2Conv(
                    (-1, -1),
                    hidden_dim,
                    heads=heads,
                    concat=False,
                    edge_dim=1,
                    dropout=dropout,
                    add_self_loops=False,
                ),
                ("Asset", "licensed_to", "Licensee"): GATv2Conv(
                    (-1, -1),
                    hidden_dim,
                    heads=heads,
                    concat=False,
                    edge_dim=1,
                    dropout=dropout,
                    add_self_loops=False,
                ),
                ("Asset", "similar_to", "Asset"): GATv2Conv(
                    (-1, -1),
                    hidden_dim,
                    heads=heads,
                    concat=False,
                    edge_dim=1,
                    dropout=dropout,
                    add_self_loops=False,
                ),
                ("Asset", "flagged_with", "Asset"): GATv2Conv(
                    (-1, -1),
                    hidden_dim,
                    heads=heads,
                    concat=False,
                    edge_dim=1,
                    dropout=dropout,
                    add_self_loops=False,
                ),
                # Reverse relations created by GraphBuilder/ToUndirected.
                ("Creator", "rev_created_by", "Asset"): GATv2Conv(
                    (-1, -1),
                    hidden_dim,
                    heads=heads,
                    concat=False,
                    edge_dim=1,
                    dropout=dropout,
                    add_self_loops=False,
                ),
                ("Licensee", "rev_licensed_to", "Asset"): GATv2Conv(
                    (-1, -1),
                    hidden_dim,
                    heads=heads,
                    concat=False,
                    edge_dim=1,
                    dropout=dropout,
                    add_self_loops=False,
                ),
            },
            aggr="sum",
        )

        self.conv2 = HeteroConv(
            {
                ("Asset", "created_by", "Creator"): GATv2Conv(
                    (-1, -1), hidden_dim, heads=1, concat=False, edge_dim=1, add_self_loops=False
                ),
                ("Asset", "licensed_to", "Licensee"): GATv2Conv(
                    (-1, -1), hidden_dim, heads=1, concat=False, edge_dim=1, add_self_loops=False
                ),
                ("Asset", "similar_to", "Asset"): GATv2Conv(
                    (-1, -1), hidden_dim, heads=1, concat=False, edge_dim=1, add_self_loops=False
                ),
                ("Asset", "flagged_with", "Asset"): GATv2Conv(
                    (-1, -1), hidden_dim, heads=1, concat=False, edge_dim=1, add_self_loops=False
                ),
                ("Creator", "rev_created_by", "Asset"): GATv2Conv(
                    (-1, -1), hidden_dim, heads=1, concat=False, edge_dim=1, add_self_loops=False
                ),
                ("Licensee", "rev_licensed_to", "Asset"): GATv2Conv(
                    (-1, -1), hidden_dim, heads=1, concat=False, edge_dim=1, add_self_loops=False
                ),
            },
            aggr="sum",
        )

        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, out_classes),
        )

    def _project_inputs(self, x_dict: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        projected: dict[str, torch.Tensor] = {}
        if "Asset" in x_dict:
            projected["Asset"] = self.asset_proj(x_dict["Asset"])
        if "Creator" in x_dict:
            projected["Creator"] = self.creator_proj(x_dict["Creator"])
        if "Licensee" in x_dict:
            projected["Licensee"] = self.licensee_proj(x_dict["Licensee"])
        return projected

    def forward(
        self,
        x_dict: dict[str, torch.Tensor],
        edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
        edge_attr_dict: dict[tuple[str, str, str], torch.Tensor],
        query_asset_index: int,
    ) -> torch.Tensor:
        x_dict = self._project_inputs(x_dict)

        x_dict = self.conv1(x_dict, edge_index_dict, edge_attr_dict=edge_attr_dict)
        x_dict = {k: F.relu(v) for k, v in x_dict.items()}
        x_dict = {k: F.dropout(v, p=self.dropout, training=self.training) for k, v in x_dict.items()}

        x_dict = self.conv2(x_dict, edge_index_dict, edge_attr_dict=edge_attr_dict)
        x_dict = {k: F.relu(v) for k, v in x_dict.items()}

        asset_state = x_dict["Asset"][query_asset_index]
        logits = self.classifier(asset_state)
        return logits

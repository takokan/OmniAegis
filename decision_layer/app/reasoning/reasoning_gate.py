from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from importlib import import_module
from typing import Any, Callable

import numpy as np
import torch
import torch.nn.functional as F

class DecisionLabel(IntEnum):
    INNOCENT = 0
    AUTHORIZED = 1
    INFRINGING = 2


@dataclass
class ReasoningResult:
    label: DecisionLabel
    confidence: float
    probabilities: dict[str, float]


class ReasoningGate:
    """Final reasoning gate that maps Stage-3 neighbors -> graph decision.

    A lightweight CPU-first inference wrapper around `HeteroGATReasoner`.
    """

    def __init__(
        self,
        model: Any = None,
        graph_builder: Any = None,
        use_compile: bool = True,
    ) -> None:
        builder_module = import_module("app.reasoning.graph_builder")
        engine_module = import_module("app.reasoning.graph_engine")
        _GraphBuilder = getattr(builder_module, "GraphBuilder")
        _HeteroGATReasoner = getattr(engine_module, "HeteroGATReasoner")

        self.device = torch.device("cpu")
        self.model = (model or _HeteroGATReasoner()).to(self.device)
        self.model.eval()

        # CPU optimization best-effort; falls back gracefully when unsupported.
        if use_compile and hasattr(torch, "compile"):
            try:
                self.model = torch.compile(self.model, mode="reduce-overhead")
            except Exception:
                pass

        self.graph_builder = graph_builder or _GraphBuilder()

    @staticmethod
    def _enrich_qdrant_results(
        qdrant_results: list[Any],
        context_fetcher: Callable[[list[str]], dict[str, dict[str, Any]]] | None,
    ) -> list[Any]:
        if context_fetcher is None:
            return qdrant_results

        asset_ids: list[str] = []
        for r in qdrant_results:
            if isinstance(r, dict):
                aid = str(r.get("asset_id", ""))
            else:
                aid = str(getattr(r, "asset_id", ""))
            if aid:
                asset_ids.append(aid)

        context = context_fetcher(asset_ids)

        enriched: list[Any] = []
        for r in qdrant_results:
            if isinstance(r, dict):
                aid = str(r.get("asset_id", ""))
                meta = dict(r.get("metadata", {}))
                merged = {**meta, **context.get(aid, {})}
                enriched.append({**r, "metadata": merged})
            else:
                aid = str(getattr(r, "asset_id", ""))
                meta = dict(getattr(r, "metadata", {}) or {})
                merged = {**meta, **context.get(aid, {})}
                setattr(r, "metadata", merged)
                enriched.append(r)

        return enriched

    @torch.no_grad()
    def reason_about_asset(
        self,
        asset_embedding: np.ndarray,
        qdrant_results: list[Any],
        query_metadata: dict[str, Any] | None = None,
        context_fetcher: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
    ) -> ReasoningResult:
        """Runs Stage-4 reasoning over a local subgraph.

        Steps:
        1) Optional context lookup for neighbors.
        2) Build `HeteroData` subgraph.
        3) GNN forward pass.
        4) Return label + confidence.
        """
        enriched_results = self._enrich_qdrant_results(qdrant_results, context_fetcher)

        graph = self.graph_builder.build_subgraph(
            query_embedding=asset_embedding,
            qdrant_results=enriched_results,
            query_metadata=query_metadata,
        )

        x_dict = {k: v.x.to(self.device) for k, v in graph.node_items()}
        edge_index_dict = {k: v.edge_index.to(self.device) for k, v in graph.edge_items()}
        edge_attr_dict = {
            k: v.edge_attr.to(self.device)
            for k, v in graph.edge_items()
            if hasattr(v, "edge_attr") and v.edge_attr is not None
        }

        query_idx = int(graph["Asset"].query_index[0].item())
        logits = self.model(
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            edge_attr_dict=edge_attr_dict,
            query_asset_index=query_idx,
        )

        probs = F.softmax(logits, dim=-1)
        pred = int(torch.argmax(probs).item())
        confidence = float(probs[pred].item())

        return ReasoningResult(
            label=DecisionLabel(pred),
            confidence=confidence,
            probabilities={
                "innocent": float(probs[DecisionLabel.INNOCENT].item()),
                "authorized": float(probs[DecisionLabel.AUTHORIZED].item()),
                "infringing": float(probs[DecisionLabel.INFRINGING].item()),
            },
        )


def reason_about_asset(
    asset_embedding: np.ndarray,
    qdrant_results: list[Any],
    query_metadata: dict[str, Any] | None = None,
    context_fetcher: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
) -> ReasoningResult:
    gate = ReasoningGate()
    return gate.reason_about_asset(
        asset_embedding=asset_embedding,
        qdrant_results=qdrant_results,
        query_metadata=query_metadata,
        context_fetcher=context_fetcher,
    )

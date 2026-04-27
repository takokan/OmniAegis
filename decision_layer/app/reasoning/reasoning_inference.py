from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import torch
from torch_geometric.data import HeteroData


@dataclass
class ReasoningInferenceResult:
    is_infringing: bool
    infringement_probability: float
    predicted_creator_id: str


class ReasoningInferenceEngine:
    """CPU-first inference wrapper for Stage-5 RightsGNN."""

    def __init__(
        self,
        model: Any,
        temperature_scaler: Any = None,
        use_compile: bool = True,
        use_jit_script: bool = False,
    ) -> None:
        self.device = torch.device("cpu")
        self.model = model.to(self.device)
        self.model.eval()

        if use_compile and hasattr(torch, "compile"):
            try:
                self.model = torch.compile(self.model, mode="reduce-overhead")
            except Exception:
                pass

        # Best-effort JIT path; dynamic hetero dict signatures may not script.
        if use_jit_script:
            try:
                self.model = torch.jit.script(self.model)
            except Exception:
                pass

        self.temperature_scaler = temperature_scaler.to(self.device) if temperature_scaler is not None else None

    @torch.no_grad()
    def predict_reasoning(self, subgraph: HeteroData, threshold: float = 0.5) -> ReasoningInferenceResult:
        # Contract guard for deterministic query extraction.
        if int(subgraph["Asset"].query_index[0].item()) != 0:
            raise ValueError("Subgraph contract violation: query Asset node must be index 0")

        x_dict = {k: v.x.to(self.device) for k, v in subgraph.node_items()}
        edge_index_dict = {k: v.edge_index.to(self.device) for k, v in subgraph.edge_items()}

        infringement_logit, attribution_logits, _ = self.model(
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            query_asset_index=0,
        )

        if self.temperature_scaler is not None:
            # Stage-6 calibration pattern: apply temperature scaling after model logit.
            infringement_probability = float(self.temperature_scaler(infringement_logit.view(1)).item())
        else:
            infringement_probability = float(torch.sigmoid(infringement_logit).item())
        is_infringing = infringement_probability >= threshold

        pred_creator_idx = int(torch.argmax(attribution_logits).item())

        creator_ids = getattr(subgraph["Creator"], "node_ids", None)
        if creator_ids and 0 <= pred_creator_idx < len(creator_ids):
            predicted_creator_id = str(creator_ids[pred_creator_idx])
        else:
            predicted_creator_id = "unknown"

        return ReasoningInferenceResult(
            is_infringing=is_infringing,
            infringement_probability=infringement_probability,
            predicted_creator_id=predicted_creator_id,
        )


def predict_reasoning(subgraph: HeteroData, model: Any = None) -> dict[str, Any]:
    if model is None:
        model_module = import_module("app.reasoning.model")
        rights_gnn_cls = getattr(model_module, "RightsGNN")
        model = rights_gnn_cls()

    engine = ReasoningInferenceEngine(model=model, use_compile=True, use_jit_script=False)
    result = engine.predict_reasoning(subgraph=subgraph)
    return {
        "is_infringing": result.is_infringing,
        "infringement_probability": result.infringement_probability,
        "predicted_creator_id": result.predicted_creator_id,
    }

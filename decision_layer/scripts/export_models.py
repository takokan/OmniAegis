from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn

from decision_layer.app.fingerprinters.semantic_embedder import SemanticEmbedder
from decision_layer.app.reasoning.model import RightsGNN


def export_models(output_dir: str = "./models") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    semantic = SemanticEmbedder(embedding_dim=512)
    semantic.feature_extractor.eval()
    semantic.projection.eval()

    rights = RightsGNN()
    rights.eval()

    # Export semantic backbone + projection using torch.jit.script.
    scripted_backbone = torch.jit.script(semantic.feature_extractor)
    scripted_projection = torch.jit.script(semantic.projection)

    scripted_backbone.save(str(out / "semantic_backbone.pt"))
    scripted_projection.save(str(out / "semantic_projection.pt"))

    # Wrapper to make RightsGNN script-friendly for dict inputs.
    class RightsWrapper(nn.Module):
        def __init__(self, m: RightsGNN) -> None:
            super().__init__()
            self.m = m

        def forward(self, x_asset, x_creator, x_licensee, edge_tensors):
            x_dict = {
                "Asset": x_asset,
                "Creator": x_creator,
                "Licensee": x_licensee,
            }
            edge_index_dict = {
                ("Asset", "created_by", "Creator"): edge_tensors[0],
                ("Asset", "licensed_to", "Licensee"): edge_tensors[1],
                ("Asset", "similar_to", "Asset"): edge_tensors[2],
                ("Asset", "flagged_with", "Asset"): edge_tensors[3],
                ("Creator", "rev_created_by", "Asset"): edge_tensors[4],
                ("Licensee", "rev_licensed_to", "Asset"): edge_tensors[5],
            }
            infringement_logit, attribution_logits, _ = self.m(
                x_dict=x_dict,
                edge_index_dict=edge_index_dict,
                query_asset_index=0,
            )
            return infringement_logit, attribution_logits

    wrapper = RightsWrapper(rights).eval()
    scripted_rights = torch.jit.script(wrapper)
    scripted_rights.save(str(out / "rights_gnn.pt"))

    print(f"Saved scripted models to {out.resolve()}")


if __name__ == "__main__":
    export_models()

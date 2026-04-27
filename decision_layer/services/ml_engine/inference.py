from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import torch


class InferenceModelLoader:
    """Loads scripted `.pt` models when available, with class fallback."""

    def __init__(self, models_dir: str = "./models", device: str = "cpu") -> None:
        self.models_dir = Path(models_dir)
        self.device = torch.device(device)

    def _load_scripted(self, path: Path) -> Any:
        return torch.jit.load(str(path), map_location=self.device)

    @staticmethod
    def _import_attr(module_path: str, attr_name: str) -> Any:
        module = import_module(module_path)
        return getattr(module, attr_name)

    def load_semantic_modules(self) -> dict[str, Any]:
        backbone_pt = self.models_dir / "semantic_backbone.pt"
        projection_pt = self.models_dir / "semantic_projection.pt"

        if backbone_pt.exists() and projection_pt.exists():
            return {
                "mode": "scripted",
                "backbone": self._load_scripted(backbone_pt),
                "projection": self._load_scripted(projection_pt),
            }

        semantic_cls = self._import_attr("app.fingerprinters.semantic_embedder", "SemanticEmbedder")
        semantic = semantic_cls(embedding_dim=512)
        return {
            "mode": "eager",
            "backbone": semantic.feature_extractor,
            "projection": semantic.projection,
        }

    def load_rights_gnn(self) -> Any:
        model_pt = self.models_dir / "rights_gnn.pt"
        if model_pt.exists():
            return self._load_scripted(model_pt)

        model_cls = self._import_attr("app.reasoning.model", "RightsGNN")
        return model_cls()

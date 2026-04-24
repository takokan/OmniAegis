from __future__ import annotations

from io import BytesIO

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, UnidentifiedImageError
from torchvision import transforms
from torchvision.models import ResNet50_Weights, resnet50


class SemanticEmbedder:
    """Stage-2 semantic embedder for derivative work detection.

    Hard contract (immutable preprocessing):
    - Resize(256)
    - CenterCrop(224)
    - ToTensor()
    - Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    CPU-first design:
    - Uses `torch.no_grad()` for inference-only path.
    - Produces NumPy float32 output for direct FAISS usage.
    """

    def __init__(self, embedding_dim: int = 512) -> None:
        self.embedding_dim = embedding_dim
        self.device = torch.device("cpu")

        weights = ResNet50_Weights.IMAGENET1K_V2
        backbone = resnet50(weights=weights)
        self.feature_extractor = nn.Sequential(*list(backbone.children())[:-1]).to(self.device)
        self.feature_extractor.eval()

        # 2048 -> 512 learned projection.
        # Initialized orthogonally for stable variance preservation and deterministic behavior.
        self.projection = nn.Linear(2048, embedding_dim, bias=False).to(self.device)
        rng_state = torch.random.get_rng_state()
        torch.manual_seed(42)
        nn.init.orthogonal_(self.projection.weight)
        torch.random.set_rng_state(rng_state)
        self.projection.eval()

        # Immutable preprocessing pipeline required by contract.
        self.transform = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def _load_rgb_image_from_bytes(self, content: bytes) -> Image.Image:
        try:
            image = Image.open(BytesIO(content)).convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("Invalid or corrupt image file for semantic embedding") from exc
        return image

    def _load_rgb_image_from_path(self, image_path: str) -> Image.Image:
        try:
            image = Image.open(image_path).convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("Invalid or corrupt image file for semantic embedding") from exc
        return image

    def _embed_image(self, image: Image.Image) -> np.ndarray:
        with torch.no_grad():
            tensor = self.transform(image).unsqueeze(0).to(self.device)  # (1, 3, 224, 224)
            features = self.feature_extractor(tensor).flatten(1)  # (1, 2048)
            projected = self.projection(features)  # (1, 512)
            normalized = F.normalize(projected, p=2, dim=1)  # unit sphere for cosine/IP
            return normalized.squeeze(0).cpu().numpy().astype(np.float32)

    def embed_from_bytes(self, content: bytes) -> dict:
        if not content:
            raise ValueError("Uploaded image is empty")
        image = self._load_rgb_image_from_bytes(content)
        embedding = self._embed_image(image)
        return {
            "embedding": embedding,
            "embedding_dim": int(self.embedding_dim),
        }

    def embed_from_path(self, image_path: str) -> dict:
        image = self._load_rgb_image_from_path(image_path)
        embedding = self._embed_image(image)
        return {
            "embedding": embedding,
            "embedding_dim": int(self.embedding_dim),
        }

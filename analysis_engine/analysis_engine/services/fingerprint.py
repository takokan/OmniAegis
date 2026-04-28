from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class FingerprintMatch:
    best_similarity: float
    best_match_id: str | None


def _dct2(a: np.ndarray) -> np.ndarray:
    # OpenCV DCT expects float32.
    return cv2.dct(a.astype(np.float32))


def _phash64_hex_from_rgb(pil_rgb: Image.Image) -> str:
    # Standard pHash-ish:
    # 1) grayscale 32x32
    # 2) DCT
    # 3) take top-left 8x8 (excluding [0,0] DC component for median)
    # 4) threshold by median to 64 bits
    img = pil_rgb.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    pixels = np.asarray(img, dtype=np.float32)
    dct = _dct2(pixels)
    low = dct[:8, :8].copy()
    med = np.median(low[1:, :].ravel())
    bits = (low > med).astype(np.uint8).reshape(-1)  # 64 bits
    out = 0
    for b in bits.tolist():
        out = (out << 1) | int(b)
    return f"{out:016x}"


def _hamming64_hex(a: str, b: str) -> int:
    try:
        x = int(a, 16) ^ int(b, 16)
    except Exception:
        return 64
    # Python 3.8+: int.bit_count exists
    return int(x.bit_count())


class FingerprintService:
    """Perceptual hashing over frames; pluggable SoT lookup.

    For now we implement:
    - pHash for frames
    - optional comparison against a small in-memory "truth" map from env/config
      (in production this should be backed by Qdrant/Redis/Postgres).
    """

    def __init__(self, *, truth_db: dict[str, str] | None = None) -> None:
        # truth_db: {truth_id: phash_hex}
        self.truth_db = truth_db or {}

    def phash_hex(self, frame_bgr: np.ndarray) -> str:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        return _phash64_hex_from_rgb(pil)

    def compare_to_truth(self, phash_hex: str) -> FingerprintMatch:
        if not self.truth_db:
            return FingerprintMatch(best_similarity=0.0, best_match_id=None)

        best_sim = 0.0
        best_id: str | None = None
        for truth_id, truth_hex in self.truth_db.items():
            try:
                dist = _hamming64_hex(phash_hex, truth_hex)
                sim = 1.0 - (float(dist) / 64.0)
                if sim > best_sim:
                    best_sim = sim
                    best_id = truth_id
            except Exception:
                continue
        return FingerprintMatch(best_similarity=float(max(min(best_sim, 1.0), 0.0)), best_match_id=best_id)


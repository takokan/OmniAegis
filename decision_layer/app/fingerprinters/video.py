from __future__ import annotations

import cv2
import numpy as np

from .image import ImageFingerprinter


class VideoFingerprinter:
    """Video fingerprint via 16 evenly spaced pHash frames.

    Uses sparse frame sampling to keep compute bounded on low-end hardware.
    """

    def __init__(self, frames_to_sample: int = 16) -> None:
        self.frames_to_sample = frames_to_sample
        self.image_fingerprinter = ImageFingerprinter()

    def _safe_frame_positions(self, total_frames: int) -> np.ndarray:
        if total_frames <= 0:
            raise ValueError("Video has no readable frames")
        if total_frames < self.frames_to_sample:
            return np.linspace(0, total_frames - 1, total_frames, dtype=int)
        return np.linspace(0, total_frames - 1, self.frames_to_sample, dtype=int)

    def fingerprint(self, video_path: str) -> dict:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("Invalid or corrupt video file")

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            positions = self._safe_frame_positions(total_frames)

            frame_hashes_hex: list[str] = []
            frame_hash_bytes: list[np.ndarray] = []

            for pos in positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                fp = self.image_fingerprinter.fingerprint(gray)
                frame_hashes_hex.append(fp["hash_hex"])
                frame_hash_bytes.append(fp["hash_bytes"])

            if not frame_hash_bytes:
                raise ValueError("No valid frames could be decoded")

            # Aggregate hash by per-bit majority vote for compact matching.
            bits_matrix = np.vstack([np.unpackbits(h) for h in frame_hash_bytes])
            majority_bits = (bits_matrix.mean(axis=0) >= 0.5).astype(np.uint8)
            aggregate_bytes = np.packbits(majority_bits)

            return {
                "frames_sampled": len(frame_hashes_hex),
                "frame_hashes": frame_hashes_hex,
                "aggregate_hash_hex": aggregate_bytes.tobytes().hex(),
                "aggregate_hash_bits": "".join(majority_bits.astype(str)),
                "aggregate_hash_bytes": aggregate_bytes,
                "hash_size_bits": 64,
            }
        finally:
            cap.release()

from __future__ import annotations

import cv2
import numpy as np


class ImageFingerprinter:
    """Fast perceptual hashing (pHash) for near-duplicate image detection.

    - Output: 64-bit fingerprint packed in 8 bytes.
    - Low-latency path: all operations are vectorized NumPy/OpenCV ops.
    """

    def __init__(self, hash_size: int = 8, highfreq_factor: int = 4) -> None:
        self.hash_size = hash_size
        self.highfreq_factor = highfreq_factor
        self.target_size = self.hash_size * self.highfreq_factor

    def fingerprint_from_bytes(self, content: bytes) -> dict:
        arr = np.frombuffer(content, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Invalid or corrupt image file")
        return self.fingerprint(image)

    def fingerprint(self, gray_image: np.ndarray) -> dict:
        if gray_image is None or gray_image.size == 0:
            raise ValueError("Empty image data")

        if gray_image.ndim == 3:
            gray_image = cv2.cvtColor(gray_image, cv2.COLOR_BGR2GRAY)

        resized = cv2.resize(
            gray_image,
            (self.target_size, self.target_size),
            interpolation=cv2.INTER_AREA,
        )

        dct = cv2.dct(np.float32(resized))
        low_freq = dct[: self.hash_size, : self.hash_size]

        # Robust median thresholding avoids bright/dark bias.
        median = np.median(low_freq)
        bits = (low_freq > median).astype(np.uint8).reshape(-1)

        packed = np.packbits(bits)
        return {
            "hash_hex": packed.tobytes().hex(),
            "hash_bits": "".join(bits.astype(str)),
            "hash_bytes": packed,
            "hash_size_bits": 64,
        }

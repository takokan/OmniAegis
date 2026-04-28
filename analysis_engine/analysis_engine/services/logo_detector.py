from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:  # optional heavy deps
    import torch
except Exception:  # pragma: no cover
    torch = None  # type: ignore[assignment]

try:  # optional heavy deps
    from ultralytics import YOLO
except Exception:  # pragma: no cover
    YOLO = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox_xyxy: list[float]


class LogoDetector:
    def __init__(self, *, enabled: bool = True, model_name: str = "yolov8n.pt") -> None:
        self.enabled = enabled and YOLO is not None
        self.model_name = model_name
        self._model = None
        self._device = "cpu"

        if self.enabled:
            self._device = self._select_device()
            self._model = YOLO(self.model_name)

    def _select_device(self) -> str:
        if torch is None:
            return "cpu"
        try:
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        if not self.enabled or self._model is None:
            return []

        # Ultralytics accepts numpy arrays (BGR OK); keep small for performance.
        results = self._model.predict(frame_bgr, device=self._device, verbose=False)
        detections: list[Detection] = []
        for r in results:
            names = getattr(r, "names", {}) or {}
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue
            for b in boxes:
                try:
                    cls_id = int(b.cls.item())
                    conf = float(b.conf.item())
                    xyxy = [float(x) for x in b.xyxy[0].tolist()]
                    detections.append(
                        Detection(
                            label=str(names.get(cls_id, cls_id)),
                            confidence=conf,
                            bbox_xyxy=xyxy,
                        )
                    )
                except Exception:
                    continue
        return detections


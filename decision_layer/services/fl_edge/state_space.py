from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, pi, sin
from typing import Any, ClassVar, Mapping, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class SentinelState:
    """Normalized state vector for the SentinelAgent RL policy.

    The requested feature list expands to 14 normalized values:
    - calibrated confidence
    - uncertainty
    - 4-dim one-hot content type
    - HITL queue depth
    - reviewer capacity
    - false positive rate
    - HITL overturn rate
    - privacy budget remaining
    - model age
    - time-of-day sin/cos encoding
    """

    calibrated_confidence: float
    uncertainty: float
    content_type_text: float
    content_type_image: float
    content_type_audio: float
    content_type_video: float
    hitl_queue_depth: float
    reviewer_capacity: float
    false_positive_rate_2h: float
    hitl_overturn_rate_2h: float
    privacy_budget: float
    model_age: float
    time_of_day_sin: float
    time_of_day_cos: float
    vector: np.ndarray = field(repr=False, compare=False)

    CONTENT_TYPES: ClassVar[tuple[str, str, str, str]] = ("text", "image", "audio", "video")
    DEFAULT_QUEUE_DEPTH_CAP: ClassVar[float] = 200.0
    DEFAULT_REVIEWER_CAPACITY_CAP: ClassVar[float] = 20.0
    DEFAULT_MODEL_AGE_CAP_DAYS: ClassVar[float] = 365.0

    @classmethod
    def from_raw(cls, data: Mapping[str, Any]) -> SentinelState:
        """Create a normalized state from raw runtime measurements."""

        confidence = cls._normalize_confidence(
            cls._pick_float(data, ("calibrated_confidence", "confidence", "score"), default=0.0)
        )
        uncertainty = cls._clip01(
            cls._pick_float(data, ("uncertainty", "dropout_variance", "variance"), default=0.0)
        )

        content_type = cls._encode_content_type(data.get("content_type"))
        queue_depth = cls._normalize_ratio(
            cls._pick_float(data, ("hitl_queue_depth", "queue_depth", "backlog"), default=0.0),
            cls.DEFAULT_QUEUE_DEPTH_CAP,
        )
        reviewer_capacity = cls._normalize_ratio(
            cls._pick_float(data, ("reviewer_capacity", "reviewer_count", "available_reviewers"), default=0.0),
            cls.DEFAULT_REVIEWER_CAPACITY_CAP,
        )
        false_positive_rate = cls._normalize_rate(
            cls._pick_float(data, ("false_positive_rate_2h", "false_positive_rate", "fp_rate_2h"), default=0.0)
        )
        overturn_rate = cls._normalize_rate(
            cls._pick_float(data, ("hitl_overturn_rate_2h", "overturn_rate", "hitl_overturn_rate"), default=0.0)
        )
        privacy_budget = cls._normalize_rate(
            cls._pick_float(data, ("privacy_budget", "privacy_budget_remaining", "budget_remaining"), default=1.0)
        )
        model_age = cls._normalize_ratio(
            cls._extract_model_age_days(data),
            cls.DEFAULT_MODEL_AGE_CAP_DAYS,
        )
        time_of_day_sin, time_of_day_cos = cls._encode_time_of_day(data)

        vector = np.asarray(
            [
                confidence,
                uncertainty,
                *content_type.tolist(),
                queue_depth,
                reviewer_capacity,
                false_positive_rate,
                overturn_rate,
                privacy_budget,
                model_age,
                time_of_day_sin,
                time_of_day_cos,
            ],
            dtype=np.float32,
        )

        return cls(
            calibrated_confidence=confidence,
            uncertainty=uncertainty,
            content_type_text=float(content_type[0]),
            content_type_image=float(content_type[1]),
            content_type_audio=float(content_type[2]),
            content_type_video=float(content_type[3]),
            hitl_queue_depth=queue_depth,
            reviewer_capacity=reviewer_capacity,
            false_positive_rate_2h=false_positive_rate,
            hitl_overturn_rate_2h=overturn_rate,
            privacy_budget=privacy_budget,
            model_age=model_age,
            time_of_day_sin=time_of_day_sin,
            time_of_day_cos=time_of_day_cos,
            vector=vector,
        )

    @staticmethod
    def _pick_float(data: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return float(default)

    @staticmethod
    def _clip01(value: float) -> float:
        return float(np.clip(value, 0.0, 1.0))

    @classmethod
    def _normalize_confidence(cls, value: float) -> float:
        if value > 1.0:
            value = value / 100.0
        return cls._clip01(value)

    @classmethod
    def _normalize_rate(cls, value: float) -> float:
        if value > 1.0:
            value = value / 100.0
        return cls._clip01(value)

    @classmethod
    def _normalize_ratio(cls, value: float, soft_cap: float) -> float:
        if soft_cap <= 0.0:
            return cls._clip01(value)
        return cls._clip01(value / soft_cap)

    @classmethod
    def _encode_content_type(cls, content_type: Any) -> np.ndarray:
        one_hot = np.zeros((4,), dtype=np.float32)
        if content_type is None:
            return one_hot

        if isinstance(content_type, str):
            normalized = content_type.strip().lower()
            alias_map = {
                "txt": "text",
                "document": "text",
                "image": "image",
                "img": "image",
                "photo": "image",
                "audio": "audio",
                "voice": "audio",
                "video": "video",
                "clip": "video",
            }
            normalized = alias_map.get(normalized, normalized)
            if normalized in cls.CONTENT_TYPES:
                one_hot[cls.CONTENT_TYPES.index(normalized)] = 1.0
            return one_hot

        if isinstance(content_type, Sequence) and not isinstance(content_type, (bytes, bytearray, str)):
            values = np.asarray(list(content_type), dtype=np.float32).reshape(-1)
            if values.size == 4:
                total = float(values.sum())
                if total > 0.0:
                    return np.clip(values / total, 0.0, 1.0).astype(np.float32)
                return one_hot

        try:
            index = int(content_type)
        except (TypeError, ValueError):
            return one_hot

        if 0 <= index < 4:
            one_hot[index] = 1.0
        return one_hot

    @staticmethod
    def _extract_model_age_days(data: Mapping[str, Any]) -> float:
        if "model_age_days" in data:
            return float(data["model_age_days"])
        if "model_age_hours" in data:
            return float(data["model_age_hours"]) / 24.0
        if "model_age" in data:
            return float(data["model_age"])
        return 0.0

    @staticmethod
    def _encode_time_of_day(data: Mapping[str, Any]) -> tuple[float, float]:
        hour_raw = data.get("hour")
        if hour_raw is None:
            hour_raw = data.get("hour_of_day", 0)
        try:
            hour = float(hour_raw) % 24.0
        except (TypeError, ValueError):
            hour = 0.0

        angle = 2.0 * pi * hour / 24.0
        sin_value = (sin(angle) + 1.0) / 2.0
        cos_value = (cos(angle) + 1.0) / 2.0
        return float(sin_value), float(cos_value)

    def as_array(self) -> np.ndarray:
        """Return the normalized state as a float32 numpy vector."""

        return self.vector.copy()

    def to_dict(self) -> dict[str, float]:
        """Return the normalized state as a serializable mapping."""

        return {
            "calibrated_confidence": self.calibrated_confidence,
            "uncertainty": self.uncertainty,
            "content_type_text": self.content_type_text,
            "content_type_image": self.content_type_image,
            "content_type_audio": self.content_type_audio,
            "content_type_video": self.content_type_video,
            "hitl_queue_depth": self.hitl_queue_depth,
            "reviewer_capacity": self.reviewer_capacity,
            "false_positive_rate_2h": self.false_positive_rate_2h,
            "hitl_overturn_rate_2h": self.hitl_overturn_rate_2h,
            "privacy_budget": self.privacy_budget,
            "model_age": self.model_age,
            "time_of_day_sin": self.time_of_day_sin,
            "time_of_day_cos": self.time_of_day_cos,
        }


__all__ = ["SentinelState"]

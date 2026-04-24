from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Modality(str, Enum):
    image = "image"
    video = "video"
    audio = "audio"


class FingerprintResponse(BaseModel):
    modality: Modality
    fingerprint: dict[str, Any]
    registered: bool = False
    asset_id: str | None = None


class MatchItem(BaseModel):
    asset_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    score: float
    metadata: dict[str, Any]


class VisualHighlight(BaseModel):
    x: int
    y: int
    width: int
    height: int
    importance: float


class ContextualFactor(BaseModel):
    factor: str
    shap_value: float


class ExplanationPayload(BaseModel):
    visual_highlights: list[VisualHighlight] = Field(default_factory=list)
    contextual_factors: list[ContextualFactor] = Field(default_factory=list)


class MatchResponse(BaseModel):
    modality: Modality
    query_summary: dict[str, Any]
    matches: list[MatchItem]
    explanation: ExplanationPayload = Field(default_factory=ExplanationPayload)

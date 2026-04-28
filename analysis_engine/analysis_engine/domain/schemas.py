from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class IngestJob(BaseModel):
    message_id: str
    url: str
    asset_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrameHash(BaseModel):
    index: int
    phash_hex: str


class LogoDetection(BaseModel):
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox_xyxy: list[float] = Field(min_length=4, max_length=4)


class AnalysisResult(BaseModel):
    schema_version: Literal["analysis_result.v1"] = "analysis_result.v1"
    analyzed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    asset_id: str
    url: str

    # Aggregate confidence that stream matches known SoT fingerprints / official broadcast cues.
    confidence: float = Field(ge=0.0, le=1.0)
    verdict: Literal["match", "no_match", "inconclusive", "dropped"] = "inconclusive"

    signals: dict[str, Any] = Field(default_factory=dict)
    frame_hashes: list[FrameHash] = Field(default_factory=list)
    logo_detections: list[LogoDetection] = Field(default_factory=list)

    error: str | None = None


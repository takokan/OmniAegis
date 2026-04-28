from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth_api import AuthUser, get_current_user

try:
    from decision_layer.services.xai_drift import KSDriftDetector
    from decision_layer.services.xai_storage import ExplainabilityStorage
    from decision_layer.services.xai_umap import UMAPProjector
except ModuleNotFoundError:  # pragma: no cover
    from services.xai_drift import KSDriftDetector
    from services.xai_storage import ExplainabilityStorage
    from services.xai_umap import UMAPProjector

router = APIRouter(prefix="/xai", tags=["xai"])


class ExplanationLogRequest(BaseModel):
    asset_id: str
    decision_id: str
    outcome: int = Field(ge=0, le=1)
    explanation_vector: list[float]
    shap_values: dict[str, float] | None = None
    saliency_map: list[list[float]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DriftDetectionRequest(BaseModel):
    current_period_start_ms: int
    current_period_end_ms: int
    reference_period_start_ms: int
    reference_period_end_ms: int
    outcome: int | None = None


class DriftResult(BaseModel):
    feature_name: str
    current_mean: float
    reference_mean: float
    current_std: float
    reference_std: float
    ks_statistic: float
    p_value: float
    is_drifted: bool
    notes: str = ""


class DriftDetectionResponse(BaseModel):
    total_features: int
    drifted_features: int
    results: list[DriftResult]


class UMAPProjectionRequest(BaseModel):
    embeddings: list[list[float]]
    cache_key: str | None = None


class UMAPProjectionResponse(BaseModel):
    projected_2d: list[list[float]]
    count: int
    dimensions: int = 2
    metric: str
    cached: bool
    generated_at_ms: int


@router.post("/explanations/log")
async def log_explanation(
    body: ExplanationLogRequest,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Log an explanation vector and outcome pair."""
    storage = getattr(request.app.state, "xai_storage", None)
    if storage is None:
        raise HTTPException(status_code=503, detail="XAI storage is not initialized")

    try:
        result = storage.log_explanation(
            asset_id=body.asset_id,
            decision_id=body.decision_id,
            outcome=body.outcome,
            explanation_vector=body.explanation_vector,
            shap_values=body.shap_values,
            saliency_map=body.saliency_map,
            metadata=body.metadata,
            timestamp_ms=int(time.time() * 1000),
        )
        return result
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to log explanation: {exc}") from exc


@router.post("/drift/detect", response_model=DriftDetectionResponse)
async def detect_drift(
    body: DriftDetectionRequest,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> DriftDetectionResponse:
    """Perform KS test on SHAP distributions between current and reference periods."""
    storage = getattr(request.app.state, "xai_storage", None)
    if storage is None:
        raise HTTPException(status_code=503, detail="XAI storage is not initialized")

    try:
        current_features = storage.get_shap_values_for_period(
            start_ms=body.current_period_start_ms,
            end_ms=body.current_period_end_ms,
            outcome=body.outcome,
        )
        reference_features = storage.get_shap_values_for_period(
            start_ms=body.reference_period_start_ms,
            end_ms=body.reference_period_end_ms,
            outcome=body.outcome,
        )

        if not current_features or not reference_features:
            raise HTTPException(
                status_code=400,
                detail="Insufficient data for drift detection in specified periods",
            )

        detector = KSDriftDetector(p_threshold=0.05)
        results = detector.detect_drift_batch(
            current_features=current_features,
            reference_features=reference_features,
        )

        drifted = detector.filter_drifted_features(results)

        return DriftDetectionResponse(
            total_features=len(results),
            drifted_features=len(drifted),
            results=[
                DriftResult(
                    feature_name=r.feature_name,
                    current_mean=r.current_mean,
                    reference_mean=r.reference_mean,
                    current_std=r.current_std,
                    reference_std=r.reference_std,
                    ks_statistic=r.ks_statistic,
                    p_value=r.p_value,
                    is_drifted=r.is_drifted,
                    notes=r.notes,
                )
                for r in results
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Drift detection failed: {exc}") from exc


@router.post("/projection/umap", response_model=UMAPProjectionResponse)
async def project_embeddings_umap(
    body: UMAPProjectionRequest,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> UMAPProjectionResponse:
    """Project 512D embeddings to 2D UMAP space with caching."""
    projector = getattr(request.app.state, "umap_projector", None)
    if projector is None:
        raise HTTPException(status_code=503, detail="UMAP projector is not initialized")

    try:
        result = projector.project(
            embeddings=body.embeddings,
            cache_key=body.cache_key,
        )
        return UMAPProjectionResponse(**result)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"UMAP projection failed: {exc}") from exc


@router.get("/health/drift")
async def drift_detection_health(
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, str]:
    """Health check for drift detection service."""
    storage = getattr(request.app.state, "xai_storage", None)
    if storage is None:
        raise HTTPException(status_code=503, detail="XAI storage not initialized")
    return {"status": "ok", "service": "drift_detection"}


@router.get("/health/umap")
async def umap_health(
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, str]:
    """Health check for UMAP projector service."""
    projector = getattr(request.app.state, "umap_projector", None)
    if projector is None:
        raise HTTPException(status_code=503, detail="UMAP projector not initialized")
    return {"status": "ok", "service": "umap_projector"}


@router.get("/graph/{asset_id}")
async def get_asset_relationship_graph(
    asset_id: str,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    graph_db = getattr(request.app.state, "graph_db", None)
    if graph_db is None:
        raise HTTPException(status_code=503, detail="Graph database is not initialized")

    normalized_asset_id = asset_id.strip()
    if not normalized_asset_id:
        raise HTTPException(status_code=400, detail="asset_id is required")

    try:
        graph = graph_db.fetch_asset_relationship_graph(normalized_asset_id)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to load graph relationships: {exc}") from exc

    if not graph.get("nodes"):
        raise HTTPException(status_code=404, detail="No graph relationships found for the requested asset")

    return graph

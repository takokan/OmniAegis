from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth_api import AuthUser, get_current_user

try:
    from decision_layer.services.hitl_monitor import HITLQueueItem, ReviewerProfile
except ModuleNotFoundError:  # pragma: no cover
    from services.hitl_monitor import HITLQueueItem, ReviewerProfile

router = APIRouter(prefix="/hitl", tags=["hitl"])


class HITLQueueItemRequest(BaseModel):
    item_id: str
    asset_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    content_type: str
    submitter_history_score: float = Field(ge=0.0, le=1.0)
    submitter_id: str | None = None
    submitted_at_ms: int | None = None
    rights_node_ids: list[str] = Field(default_factory=list)
    creator_org_id: str | None = None
    licensee_org_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewerProfileRequest(BaseModel):
    reviewer_id: str
    organization_ids: list[str] = Field(default_factory=list)
    restricted_rights_node_ids: list[str] = Field(default_factory=list)
    blocked_submitter_ids: list[str] = Field(default_factory=list)


class AssignmentRequest(BaseModel):
    reviewer: ReviewerProfileRequest
    scan_limit: int = Field(default=50, ge=1, le=500)


class QueueItemResponse(BaseModel):
    item_id: str
    priority_score: float


class AssignmentResponse(BaseModel):
    item_id: str
    asset_id: str
    priority_score: float
    assigned_to: str
    lock_ttl_seconds: int
    coi_status: str


@router.post("/queue/items", response_model=QueueItemResponse)
async def enqueue_hitl_item(
    body: HITLQueueItemRequest,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> QueueItemResponse:
    service = getattr(request.app.state, "hitl_monitor", None)
    if service is None:
        raise HTTPException(status_code=503, detail="HITL monitor is not initialized")

    try:
        item_kwargs: dict[str, Any] = {
            "item_id": body.item_id,
            "asset_id": body.asset_id,
            "confidence": body.confidence,
            "content_type": body.content_type,
            "submitter_history_score": body.submitter_history_score,
            "submitter_id": body.submitter_id,
            "rights_node_ids": body.rights_node_ids,
            "creator_org_id": body.creator_org_id,
            "licensee_org_id": body.licensee_org_id,
            "metadata": body.metadata,
        }
        if body.submitted_at_ms is not None:
            item_kwargs["submitted_at_ms"] = body.submitted_at_ms

        item = HITLQueueItem(**item_kwargs)
        payload = service.enqueue_item(item)
        return QueueItemResponse(**payload)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to enqueue HITL item: {exc}") from exc


@router.post("/assignments/next", response_model=AssignmentResponse)
async def assign_next_hitl_item(
    body: AssignmentRequest,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> AssignmentResponse:
    service = getattr(request.app.state, "hitl_monitor", None)
    if service is None:
        raise HTTPException(status_code=503, detail="HITL monitor is not initialized")

    reviewer = ReviewerProfile(
        reviewer_id=body.reviewer.reviewer_id,
        organization_ids=body.reviewer.organization_ids,
        restricted_rights_node_ids=body.reviewer.restricted_rights_node_ids,
        blocked_submitter_ids=body.reviewer.blocked_submitter_ids,
    )

    try:
        payload = service.assign_next_item(reviewer=reviewer, scan_limit=body.scan_limit)
        if payload is None:
            raise HTTPException(status_code=404, detail="No assignable HITL item found")
        return AssignmentResponse(**payload)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to assign HITL item: {exc}") from exc


@router.post("/queue/recompute")
async def recompute_hitl_priorities(
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, int]:
    service = getattr(request.app.state, "hitl_monitor", None)
    if service is None:
        raise HTTPException(status_code=503, detail="HITL monitor is not initialized")

    try:
        updated = int(service.recompute_all_priorities())
        return {"updated": updated}
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to recompute HITL priorities: {exc}") from exc


@router.post("/assignments/reclaim-expired")
async def reclaim_expired_hitl_assignments(
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, int]:
    service = getattr(request.app.state, "hitl_monitor", None)
    if service is None:
        raise HTTPException(status_code=503, detail="HITL monitor is not initialized")

    try:
        reclaimed = int(service.reclaim_expired_assignments())
        return {"reclaimed": reclaimed}
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to reclaim expired assignments: {exc}") from exc


@router.get("/queue/stats")
async def hitl_queue_stats(
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, int]:
    service = getattr(request.app.state, "hitl_monitor", None)
    if service is None:
        raise HTTPException(status_code=503, detail="HITL monitor is not initialized")

    try:
        return dict(service.queue_stats())
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to read HITL queue stats: {exc}") from exc

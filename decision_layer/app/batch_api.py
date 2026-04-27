from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth_api import AuthUser, get_current_user, require_admin
from app.schemas import MerkleProofResponse

router = APIRouter(tags=["audit"])


# Request/Response schemas for disputes and governance
class DisputeRequest(BaseModel):
    creator_address: str
    """Creator Ethereum address (0x-prefixed)."""


class DisputeResponse(BaseModel):
    dispute_id: str
    decision_id: str
    creator_address: str
    status: str
    on_chain_status: dict | None
    merkle_proof: dict
    created_at: int


class PolicyProposalRequest(BaseModel):
    policy_id: str
    """Policy identifier."""
    policy_hash: str
    """Keccak256 hash of policy content."""
    valid_from: int
    """Unix timestamp when policy becomes valid."""


class PolicyProposalResponse(BaseModel):
    proposal_id: str
    policy_id: str
    nonce: int
    status: str
    required_signatures: int
    collected_signatures: int
    created_at: int


class CollectSignatureRequest(BaseModel):
    proposal_id: str
    """Proposal UUID."""
    signer_address: str
    """Signer Ethereum address (0x-prefixed)."""
    signature: str
    """65-byte EIP-191 signature (0x-prefixed hex)."""


class CollectSignatureResponse(BaseModel):
    proposal_id: str
    signer: str
    collected_signatures: int
    required_signatures: int
    ready_to_anchor: bool


class AnchorPolicyRequest(BaseModel):
    proposal_id: str
    """Proposal UUID with collected signatures."""


class AnchorPolicyResponse(BaseModel):
    proposal_id: str
    status: str
    tx_hash: str
    gas_used: int
    latency_seconds: float


@router.get("/get-merkle-proof/{decision_id}", response_model=MerkleProofResponse)
async def get_merkle_proof(
    decision_id: str,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> MerkleProofResponse:
    """Returns the Merkle proof path for a decision anchored by BatchCoordinator."""
    coordinator = getattr(request.app.state, "batch_coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="BatchCoordinator is not initialized")

    try:
        payload = await coordinator.get_merkle_proof(decision_id)
        return MerkleProofResponse(**payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to build Merkle proof: {exc}") from exc


@router.post("/dispute/{asset_hash}", response_model=DisputeResponse)
async def create_dispute(
    asset_hash: str,
    body: DisputeRequest,
    request: Request,
    _current_user: AuthUser = Depends(get_current_user),
) -> DisputeResponse:
    """Creates a dispute for a decision with on-chain status and Merkle proof."""
    coordinator = getattr(request.app.state, "batch_coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="BatchCoordinator is not initialized")

    try:
        payload = await coordinator.create_dispute(asset_hash, body.creator_address)
        return DisputeResponse(**payload)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to create dispute: {exc}") from exc


@router.post("/propose-policy", response_model=PolicyProposalResponse)
async def propose_policy(
    body: PolicyProposalRequest,
    request: Request,
    _current_user: AuthUser = Depends(require_admin),
) -> PolicyProposalResponse:
    """Creates a governance policy proposal awaiting signature collection (2-of-3 required)."""
    coordinator = getattr(request.app.state, "batch_coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="BatchCoordinator is not initialized")

    try:
        payload = await coordinator.propose_policy(body.policy_id, body.policy_hash, body.valid_from)
        return PolicyProposalResponse(**payload)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to create proposal: {exc}") from exc


@router.post("/collect-signature", response_model=CollectSignatureResponse)
async def collect_signature(
    body: CollectSignatureRequest,
    request: Request,
    _current_user: AuthUser = Depends(require_admin),
) -> CollectSignatureResponse:
    """Collects and validates a signature for a policy proposal."""
    coordinator = getattr(request.app.state, "batch_coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="BatchCoordinator is not initialized")

    try:
        payload = await coordinator.collect_signature(
            body.proposal_id,
            body.signer_address,
            body.signature,
        )
        return CollectSignatureResponse(**payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to collect signature: {exc}") from exc


@router.post("/anchor-policy", response_model=AnchorPolicyResponse)
async def anchor_policy(
    body: AnchorPolicyRequest,
    request: Request,
    _current_user: AuthUser = Depends(require_admin),
) -> AnchorPolicyResponse:
    """Anchors a policy proposal on-chain after 2-of-3 signatures collected."""
    coordinator = getattr(request.app.state, "batch_coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="BatchCoordinator is not initialized")

    try:
        payload = await coordinator.anchor_policy_on_chain(body.proposal_id)
        return AnchorPolicyResponse(**payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Failed to anchor policy: {exc}") from exc

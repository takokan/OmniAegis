from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

try:
    from decision_layer.shared import get_redis_client
except ModuleNotFoundError:  # pragma: no cover
    from shared import get_redis_client


router = APIRouter(prefix="/governance", tags=["governance"])
AUDIT_STREAM_KEY = os.getenv("SENTINEL_BLOCKCHAIN_AUDIT_STREAM_KEY", "sentinel:blockchain:audit:stream")


def _decode_redis_value(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _normalize_audit_entry(fields: dict[str, Any], entry_id: str) -> dict[str, Any]:
    details_raw = fields.get("details", "")
    if isinstance(details_raw, dict):
        details = details_raw
    else:
        try:
            details = json.loads(_decode_redis_value(details_raw))
        except Exception:
            details = {"message": _decode_redis_value(details_raw)}

    return {
        "id": _decode_redis_value(fields.get("id", entry_id)),
        "action": _decode_redis_value(fields.get("action", "SIMULATED_EVENT")),
        "timestamp": _decode_redis_value(fields.get("timestamp", datetime.now(timezone.utc).isoformat())),
        "policyVersion": _decode_redis_value(fields.get("policyVersion", "sim-v1")),
        "reasoningHash": _decode_redis_value(fields.get("reasoningHash", f"sim-{uuid4().hex}")),
        "admin": _decode_redis_value(fields.get("admin", "simulator@omniaegis.ai")),
        "details": details if isinstance(details, str) else json.dumps(details),
    }


@router.get("/audit")
async def list_audit_entries(limit: int = 100) -> dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")

    redis_client = await get_redis_client()
    entries = await redis_client.xrevrange(AUDIT_STREAM_KEY, count=limit)

    normalized: list[dict[str, Any]] = []
    for entry_id, fields in entries:
        normalized.append(_normalize_audit_entry(fields, _decode_redis_value(entry_id)))

    return {"entries": normalized, "total": len(normalized)}


@router.post("/audit")
async def append_audit_entry(payload: dict[str, Any]) -> dict[str, Any]:
    redis_client = await get_redis_client()
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": str(payload.get("id") or f"AUD-{uuid4().hex[:12]}"),
        "action": str(payload.get("action") or "SIMULATED_EVENT"),
        "timestamp": str(payload.get("timestamp") or now),
        "policyVersion": str(payload.get("policyVersion") or "sim-v1"),
        "reasoningHash": str(payload.get("reasoningHash") or f"0x{uuid4().hex}{uuid4().hex}"),
        "admin": str(payload.get("admin") or "simulator@omniaegis.ai"),
        "details": json.dumps(payload.get("details") or {"source": "simulator"}, ensure_ascii=True),
    }

    stream_id = await redis_client.xadd(AUDIT_STREAM_KEY, entry)
    return {"ok": True, "stream_id": _decode_redis_value(stream_id), "entry": _normalize_audit_entry(entry, str(stream_id))}

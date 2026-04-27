from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import redis  # type: ignore[reportMissingImports]

try:
    from decision_layer.services.graph_db import GraphDBService
except ModuleNotFoundError:  # pragma: no cover
    from services.graph_db import GraphDBService


@dataclass(frozen=True)
class HITLMonitorConfig:
    """Configuration contract for HITL queueing and assignment lifecycle."""

    redis_url: str = "redis://localhost:6379/0"
    max_connections: int = 64
    queue_key: str = "sentinel:hitl:review_queue"
    inflight_key: str = "sentinel:hitl:inflight"
    item_prefix: str = "sentinel:hitl:item"
    lock_prefix: str = "sentinel:hitl:lock"
    lock_ttl_seconds: int = 1800
    maintenance_interval_seconds: int = 300


@dataclass(frozen=True)
class HITLQueueItem:
    """Canonical payload persisted for each HITL review candidate."""

    item_id: str
    asset_id: str
    confidence: float
    content_type: str
    submitter_history_score: float
    submitter_id: str | None = None
    submitted_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    rights_node_ids: list[str] = field(default_factory=list)
    creator_org_id: str | None = None
    licensee_org_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewerProfile:
    """Reviewer profile used by COI filtering before assignment."""

    reviewer_id: str
    organization_ids: list[str] = field(default_factory=list)
    restricted_rights_node_ids: list[str] = field(default_factory=list)
    blocked_submitter_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class COICheckResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


class HITLMonitorError(RuntimeError):
    """Raised when HITL queue lifecycle operations fail."""


class HITLMonitorService:
    """Redis-backed HITL monitor with weighted priority, locks, and COI filtering."""

    # KEYS: [queue_key, inflight_key]
    # ARGV: [item_id, reviewer_id, now_ms, ttl_ms, lock_key]
    _CLAIM_ITEM_LUA = """
    local queue_key = KEYS[1]
    local inflight_key = KEYS[2]

    local item_id = ARGV[1]
    local reviewer_id = ARGV[2]
    local now_ms = tonumber(ARGV[3])
    local ttl_ms = tonumber(ARGV[4])
    local lock_key = ARGV[5]

    local score = redis.call('ZSCORE', queue_key, item_id)
    if not score then
        return {0, ''}
    end

    if redis.call('EXISTS', lock_key) == 1 then
        return {0, ''}
    end

    redis.call('ZREM', queue_key, item_id)
    redis.call('ZADD', inflight_key, now_ms + ttl_ms, item_id)
    redis.call(
        'SET',
        lock_key,
        cjson.encode({ reviewer_id = reviewer_id, assigned_at_ms = now_ms, expires_at_ms = now_ms + ttl_ms, priority_score = tonumber(score) }),
        'PX',
        ttl_ms
    )

    return {1, tostring(score)}
    """

    def __init__(self, config: HITLMonitorConfig | None = None, graph_db: GraphDBService | None = None) -> None:
        self.config = config or HITLMonitorConfig(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "64")),
            queue_key=os.getenv("HITL_QUEUE_KEY", "sentinel:hitl:review_queue"),
            inflight_key=os.getenv("HITL_INFLIGHT_KEY", "sentinel:hitl:inflight"),
            item_prefix=os.getenv("HITL_ITEM_PREFIX", "sentinel:hitl:item"),
            lock_prefix=os.getenv("HITL_LOCK_PREFIX", "sentinel:hitl:lock"),
            lock_ttl_seconds=int(os.getenv("HITL_LOCK_TTL_SECONDS", "1800")),
            maintenance_interval_seconds=int(os.getenv("HITL_MAINTENANCE_INTERVAL_SECONDS", "300")),
        )
        self.graph_db = graph_db
        self._pool = redis.ConnectionPool.from_url(
            self.config.redis_url,
            decode_responses=True,
            max_connections=self.config.max_connections,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        self._claim_sha = self._client.script_load(self._CLAIM_ITEM_LUA)

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            self._pool.disconnect(inuse_connections=True)

    def enqueue_item(self, item: HITLQueueItem) -> dict[str, Any]:
        score = self.compute_composite_priority(item=item)
        key = self._item_key(item.item_id)
        payload = self._serialize_item(item=item, score=score)

        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.hset(key, mapping=payload)
            pipe.zadd(self.config.queue_key, {item.item_id: score})
            pipe.execute()
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to enqueue HITL item: {exc}") from exc

        return {"item_id": item.item_id, "priority_score": score}

    def recompute_all_priorities(self, now_ms: int | None = None) -> int:
        now_ms = now_ms or int(time.time() * 1000)

        try:
            item_ids = self._client.zrange(self.config.queue_key, 0, -1)
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to enumerate HITL queue for recompute: {exc}") from exc

        updated = 0
        for item_id in item_ids:
            item = self.get_item(item_id)
            if item is None:
                continue
            score = self.compute_composite_priority(item=item, now_ms=now_ms)
            try:
                pipe = self._client.pipeline(transaction=True)
                pipe.hset(self._item_key(item_id), "last_priority_score", f"{score:.8f}")
                pipe.zadd(self.config.queue_key, {item_id: score})
                pipe.execute()
                updated += 1
            except redis.RedisError as exc:  # pragma: no cover
                raise HITLMonitorError(f"Failed to update priority for item {item_id}: {exc}") from exc

        return updated

    def reclaim_expired_assignments(self, now_ms: int | None = None) -> int:
        now_ms = now_ms or int(time.time() * 1000)

        try:
            expired_item_ids = self._client.zrangebyscore(self.config.inflight_key, min="-inf", max=now_ms)
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to query expired HITL assignments: {exc}") from exc

        reclaimed = 0
        for item_id in expired_item_ids:
            lock_key = self._lock_key(item_id)
            try:
                if self._client.exists(lock_key):
                    continue
                score = self._read_last_priority_score(item_id)
                pipe = self._client.pipeline(transaction=True)
                pipe.zrem(self.config.inflight_key, item_id)
                pipe.zadd(self.config.queue_key, {item_id: score})
                pipe.execute()
                reclaimed += 1
            except redis.RedisError as exc:  # pragma: no cover
                raise HITLMonitorError(f"Failed to reclaim expired assignment for item {item_id}: {exc}") from exc

        return reclaimed

    def pop_highest_priority_item(self, reviewer_id: str) -> dict[str, Any] | None:
        """Pop the current highest-priority item and place a 30-minute lock."""

        try:
            candidate_ids = self._client.zrevrange(self.config.queue_key, 0, 0)
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to read top HITL queue item: {exc}") from exc

        if not candidate_ids:
            return None

        item_id = str(candidate_ids[0])
        item = self.get_item(item_id)
        if item is None:
            return None

        claim = self._claim_item_atomically(item_id=item_id, reviewer_id=reviewer_id)
        if claim is None:
            return None

        return {
            "item_id": item_id,
            "asset_id": item.asset_id,
            "priority_score": claim["priority_score"],
            "assigned_to": reviewer_id,
            "lock_ttl_seconds": self.config.lock_ttl_seconds,
        }

    def assign_next_item(self, reviewer: ReviewerProfile, scan_limit: int = 50) -> dict[str, Any] | None:
        try:
            candidate_ids = self._client.zrevrange(self.config.queue_key, 0, max(scan_limit - 1, 0))
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to read HITL queue candidates: {exc}") from exc

        for item_id in candidate_ids:
            item = self.get_item(item_id)
            if item is None:
                continue

            coi_result = self.check_conflict_of_interest(item=item, reviewer=reviewer)
            if not coi_result.allowed:
                continue

            claim = self._claim_item_atomically(item_id=item_id, reviewer_id=reviewer.reviewer_id)
            if claim is None:
                continue

            return {
                "item_id": item_id,
                "asset_id": item.asset_id,
                "priority_score": claim["priority_score"],
                "assigned_to": reviewer.reviewer_id,
                "lock_ttl_seconds": self.config.lock_ttl_seconds,
                "coi_status": "clear",
            }

        return None

    def check_conflict_of_interest(self, item: HITLQueueItem, reviewer: ReviewerProfile) -> COICheckResult:
        reasons: list[str] = []

        reviewer_orgs = {org.strip().lower() for org in reviewer.organization_ids if org and org.strip()}
        reviewer_rights_nodes = {
            node.strip().lower() for node in reviewer.restricted_rights_node_ids if node and node.strip()
        }
        blocked_submitters = {s.strip().lower() for s in reviewer.blocked_submitter_ids if s and s.strip()}

        if item.submitter_id and item.submitter_id.strip().lower() in blocked_submitters:
            reasons.append("Reviewer is blocked from this submitter")

        item_orgs = {
            str(org).strip().lower()
            for org in [item.creator_org_id, item.licensee_org_id]
            if org and str(org).strip()
        }
        if reviewer_orgs.intersection(item_orgs):
            reasons.append("Reviewer organization overlaps with asset organization")

        item_rights_nodes = {node.strip().lower() for node in item.rights_node_ids if node and node.strip()}
        graph_nodes = self._collect_graph_nodes_for_item(item)

        if reviewer_rights_nodes.intersection(item_rights_nodes.union(graph_nodes)):
            reasons.append("Reviewer restricted rights-graph node overlaps with item context")

        return COICheckResult(allowed=not reasons, reasons=reasons)

    def get_item(self, item_id: str) -> HITLQueueItem | None:
        try:
            raw = self._client.hgetall(self._item_key(item_id))
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to read HITL item {item_id}: {exc}") from exc

        if not raw:
            return None

        return HITLQueueItem(
            item_id=item_id,
            asset_id=str(raw.get("asset_id", "")),
            confidence=float(raw.get("confidence", "0")),
            content_type=str(raw.get("content_type", "unknown")),
            submitter_history_score=float(raw.get("submitter_history_score", "0")),
            submitter_id=raw.get("submitter_id") or None,
            submitted_at_ms=int(raw.get("submitted_at_ms", str(int(time.time() * 1000)))),
            rights_node_ids=self._loads_json_list(raw.get("rights_node_ids", "[]")),
            creator_org_id=raw.get("creator_org_id") or None,
            licensee_org_id=raw.get("licensee_org_id") or None,
            metadata=self._loads_json_dict(raw.get("metadata", "{}")),
        )

    def queue_stats(self) -> dict[str, int]:
        try:
            queued = int(self._client.zcard(self.config.queue_key))
            inflight = int(self._client.zcard(self.config.inflight_key))
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to read HITL queue stats: {exc}") from exc
        return {"queued": queued, "inflight": inflight}

    async def run_maintenance_loop(self, stop_event: asyncio.Event) -> None:
        """Background maintenance loop that runs every 5 minutes by default."""

        while not stop_event.is_set():
            try:
                self.recompute_all_priorities()
                self.reclaim_expired_assignments()
            except Exception:
                # Background loop should not crash app lifecycle.
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.config.maintenance_interval_seconds)
            except asyncio.TimeoutError:
                continue

    def compute_composite_priority(self, item: HITLQueueItem, now_ms: int | None = None) -> float:
        """Compute weighted queue priority.

        Weights:
        - 40% confidence component (interpreted as uncertainty => `1 - confidence`)
        - 20% content type risk factor
        - 25% submitter history factor
        - 15% time-in-queue factor
        """

        now_ms = now_ms or int(time.time() * 1000)

        confidence_value = min(max(float(item.confidence), 0.0), 1.0)
        confidence_component = 1.0 - confidence_value

        content_component = self._content_type_factor(item.content_type)
        submitter_component = min(max(float(item.submitter_history_score), 0.0), 1.0)

        age_ms = max(0, now_ms - int(item.submitted_at_ms))
        max_age_ms = 24 * 60 * 60 * 1000
        time_component = min(age_ms / max_age_ms, 1.0)

        raw_score = (
            0.40 * confidence_component
            + 0.20 * content_component
            + 0.25 * submitter_component
            + 0.15 * time_component
        )
        return float(round(raw_score * 1000.0, 6))

    def _claim_item_atomically(self, item_id: str, reviewer_id: str) -> dict[str, float] | None:
        lock_key = self._lock_key(item_id)
        now_ms = int(time.time() * 1000)
        ttl_ms = int(self.config.lock_ttl_seconds * 1000)

        try:
            result = self._client.evalsha(
                self._claim_sha,
                2,
                self.config.queue_key,
                self.config.inflight_key,
                item_id,
                reviewer_id,
                str(now_ms),
                str(ttl_ms),
                lock_key,
            )
        except redis.exceptions.NoScriptError:
            self._claim_sha = self._client.script_load(self._CLAIM_ITEM_LUA)
            result = self._client.evalsha(
                self._claim_sha,
                2,
                self.config.queue_key,
                self.config.inflight_key,
                item_id,
                reviewer_id,
                str(now_ms),
                str(ttl_ms),
                lock_key,
            )
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to atomically claim HITL item {item_id}: {exc}") from exc

        if not isinstance(result, list) or len(result) < 2:
            return None

        claimed = int(result[0]) == 1
        if not claimed:
            return None

        return {"priority_score": float(result[1])}

    def _collect_graph_nodes_for_item(self, item: HITLQueueItem) -> set[str]:
        nodes: set[str] = set()
        if self.graph_db is None:
            return nodes

        try:
            neighborhood = self.graph_db.fetch_asset_neighborhood(asset_id=item.asset_id, limit_assets=32)
        except Exception:
            return nodes

        for neighbor in neighborhood.get("neighbors", []):
            creator_id = str(neighbor.get("creator_id", "")).strip().lower()
            licensee_id = str(neighbor.get("licensee_id", "")).strip().lower()
            if creator_id:
                nodes.add(creator_id)
            if licensee_id:
                nodes.add(licensee_id)

        return nodes

    def _content_type_factor(self, content_type: str) -> float:
        key = (content_type or "unknown").strip().lower()
        table = {
            "video": 1.0,
            "image": 0.8,
            "audio": 0.7,
            "document": 0.6,
            "text": 0.5,
            "unknown": 0.4,
        }
        return float(table.get(key, 0.4))

    def _serialize_item(self, item: HITLQueueItem, score: float) -> dict[str, str]:
        return {
            "asset_id": item.asset_id,
            "confidence": f"{float(item.confidence):.8f}",
            "content_type": item.content_type,
            "submitter_history_score": f"{float(item.submitter_history_score):.8f}",
            "submitter_id": item.submitter_id or "",
            "submitted_at_ms": str(int(item.submitted_at_ms)),
            "rights_node_ids": json.dumps(item.rights_node_ids),
            "creator_org_id": item.creator_org_id or "",
            "licensee_org_id": item.licensee_org_id or "",
            "metadata": json.dumps(item.metadata),
            "last_priority_score": f"{float(score):.8f}",
        }

    def _read_last_priority_score(self, item_id: str) -> float:
        try:
            raw = self._client.hget(self._item_key(item_id), "last_priority_score")
        except redis.RedisError as exc:  # pragma: no cover
            raise HITLMonitorError(f"Failed to read cached priority score for item {item_id}: {exc}") from exc

        if raw is None:
            return 0.0
        try:
            return float(raw)
        except ValueError:
            return 0.0

    def _item_key(self, item_id: str) -> str:
        return f"{self.config.item_prefix}:{item_id}"

    def _lock_key(self, item_id: str) -> str:
        return f"{self.config.lock_prefix}:{item_id}"

    @staticmethod
    def _loads_json_list(value: str) -> list[str]:
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                return []
            return [str(x) for x in parsed]
        except Exception:
            return []

    @staticmethod
    def _loads_json_dict(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except Exception:
            return {}


__all__ = [
    "COICheckResult",
    "HITLMonitorConfig",
    "HITLMonitorError",
    "HITLMonitorService",
    "HITLQueueItem",
    "ReviewerProfile",
]

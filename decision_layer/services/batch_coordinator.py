from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from prometheus_client import Counter, Gauge, Histogram
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider

from .audit_service import TransactionSigner

logger = logging.getLogger(__name__)


BLOCKCHAIN_ANCHOR_LATENCY_SECONDS = Histogram(
    "blockchain_anchor_latency_seconds",
    "Latency for anchoring or governance blockchain transactions",
    labelnames=("action",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0),
)
BLOCKCHAIN_GAS_USED_TOTAL = Counter(
    "blockchain_gas_used_total",
    "Total gas used by blockchain transactions",
    labelnames=("action",),
)
IPFS_UPLOAD_SUCCESS_RATE = Gauge(
    "ipfs_upload_success_rate",
    "Ratio of successful IPFS fetch/upload operations",
)
_IPFS_OPERATION_ATTEMPTS = Counter(
    "ipfs_operation_attempts_total",
    "Internal IPFS operation attempts",
    labelnames=("operation",),
)
_IPFS_OPERATION_SUCCESSES = Counter(
    "ipfs_operation_successes_total",
    "Internal IPFS operation successes",
    labelnames=("operation",),
)


_SENTINEL_AUDIT_MIN_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "decisionExists",
        "stateMutability": "view",
        "inputs": [{"name": "decisionId", "type": "bytes32"}],
        "outputs": [{"name": "exists", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "getDecision",
        "stateMutability": "view",
        "inputs": [{"name": "decisionId", "type": "bytes32"}],
        "outputs": [
            {"name": "evidenceCidHash", "type": "bytes32"},
            {"name": "gateway", "type": "address"},
            {"name": "timestamp", "type": "uint64"},
            {"name": "policyId", "type": "uint64"},
            {"name": "riskScoreBps", "type": "uint32"},
            {"name": "action", "type": "uint8"},
            {"name": "highStakes", "type": "bool"},
        ],
    },
]

_POLICY_REGISTRY_MIN_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "upsertPolicy",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "policyId", "type": "bytes32"},
            {"name": "policyHash", "type": "bytes32"},
            {"name": "validFrom", "type": "uint64"},
            {"name": "nonce", "type": "uint64"},
            {"name": "signatures", "type": "bytes[]"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "revokePolicy",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "policyId", "type": "bytes32"},
            {"name": "nonce", "type": "uint64"},
            {"name": "signatures", "type": "bytes[]"},
        ],
        "outputs": [],
    },
]


class BatchCoordinatorError(RuntimeError):
    """Base error for Merkle batch coordination."""


@dataclass(frozen=True, slots=True)
class BatchCoordinatorConfig:
    """Runtime configuration for 10-minute decision batching and anchoring."""

    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/omniaegis"
    merkle_anchor_contract: str = ""
    polygon_rpc_url: str = "http://127.0.0.1:8545"
    chain_id: int = 137
    anchor_interval_seconds: int = 600
    hash_algorithm: str = "sha256"
    min_confidence_scale: int = 1_000_000
    pending_manifest_prefix: str = "postgres://merkle-batches"
    retry_backoff_seconds: float = 1.0
    max_tx_delay_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "BatchCoordinatorConfig":
        return cls(
            postgres_dsn=os.getenv("POSTGRES_DSN", os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/omniaegis")),
            merkle_anchor_contract=os.getenv("MERKLE_ANCHOR_CONTRACT", ""),
            polygon_rpc_url=os.getenv("POLYGON_RPC_URL", "http://127.0.0.1:8545"),
            chain_id=int(os.getenv("POLYGON_CHAIN_ID", "137")),
            anchor_interval_seconds=int(os.getenv("MERKLE_ANCHOR_INTERVAL_SECONDS", "600")),
            hash_algorithm=os.getenv("MERKLE_HASH_ALGORITHM", "sha256").strip().lower(),
            min_confidence_scale=int(os.getenv("MERKLE_CONFIDENCE_SCALE", "1000000")),
            pending_manifest_prefix=os.getenv("MERKLE_MANIFEST_PREFIX", "postgres://merkle-batches"),
            retry_backoff_seconds=float(os.getenv("MERKLE_TX_RETRY_BACKOFF_SECONDS", "1.0")),
            max_tx_delay_seconds=float(os.getenv("MERKLE_TX_MAX_DELAY_SECONDS", "30.0")),
        )


@dataclass(frozen=True, slots=True)
class DecisionLeaf:
    """Canonical decision leaf used for Merkle construction."""

    decision_id: str
    asset_hash: bytes
    action: int
    confidence: float
    timestamp: int
    canonical_bytes: bytes = field(repr=False)
    leaf_hash: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class MerkleNode:
    """In-memory Merkle node representation mirrored into PostgreSQL."""

    batch_id: str
    level: int
    position: int
    node_hash: bytes
    left_hash: bytes | None = None
    right_hash: bytes | None = None
    decision_id: str | None = None
    is_leaf: bool = False


@dataclass(frozen=True, slots=True)
class MerkleBatch:
    """Prepared batch metadata."""

    batch_id: str
    window_start: int
    window_end: int
    leaf_count: int
    merkle_root: bytes
    manifest_uri: str
    hash_algorithm: str
    created_at: int


class BatchCoordinator:
    """Collects decisions over a rolling 10-minute window and anchors Merkle roots on-chain.

    Guarantees:
    - Decisions are written to PostgreSQL immediately and do not block inference.
    - Every 10-minute cycle builds a canonical Merkle tree from unbatched decisions.
    - Full tree nodes are persisted for independent proof reconstruction.
    - The resulting root is anchored on Polygon through the MerkleAnchor contract.
    """

    def __init__(
        self,
        signer: TransactionSigner,
        config: BatchCoordinatorConfig | None = None,
        contract_abi: list[dict[str, Any]] | None = None,
        sentinel_audit_contract: str | None = None,
        policy_registry_contract: str | None = None,
    ) -> None:
        self.config = config or BatchCoordinatorConfig.from_env()
        self._signer = signer
        self._web3 = AsyncWeb3(AsyncHTTPProvider(self.config.polygon_rpc_url))
        self._contract_address = self.config.merkle_anchor_contract.strip()
        self._sentinel_audit_contract = sentinel_audit_contract or os.getenv("SENTINEL_AUDIT_CONTRACT", "")
        self._policy_registry_contract = policy_registry_contract or os.getenv("POLICY_REGISTRY_CONTRACT", "")
        self._http = httpx.AsyncClient(timeout=5.0)
        self._contract_abi = contract_abi or [
            {
                "type": "function",
                "name": "anchorRoot",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "merkleRoot", "type": "bytes32"},
                    {"name": "startDecisionIndex", "type": "uint64"},
                    {"name": "leafCount", "type": "uint32"},
                    {"name": "manifestCid", "type": "string"},
                ],
                "outputs": [{"name": "batchId", "type": "uint64"}],
            },
            {
                "type": "function",
                "name": "anchorBatch",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "merkleRoot", "type": "bytes32"},
                    {"name": "startDecisionIndex", "type": "uint64"},
                    {"name": "leafCount", "type": "uint32"},
                    {"name": "manifestCid", "type": "string"},
                ],
                "outputs": [{"name": "batchId", "type": "uint64"}],
            },
        ]
        self._contract = None
        self._sentinel_audit = None
        self._policy_registry = None
        if self._contract_address:
            self._contract = self._web3.eth.contract(
                address=AsyncWeb3.to_checksum_address(self._contract_address),
                abi=self._contract_abi,
            )
        if self._sentinel_audit_contract:
            self._sentinel_audit = self._web3.eth.contract(
                address=AsyncWeb3.to_checksum_address(self._sentinel_audit_contract),
                abi=_SENTINEL_AUDIT_MIN_ABI,
            )
        if self._policy_registry_contract:
            self._policy_registry = self._web3.eth.contract(
                address=AsyncWeb3.to_checksum_address(self._policy_registry_contract),
                abi=_POLICY_REGISTRY_MIN_ABI,
            )

        self._pool = ConnectionPool(conninfo=self.config.postgres_dsn, kwargs={"autocommit": False, "row_factory": dict_row})
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._window_cursor_unix = int(time.time()) - int(self.config.anchor_interval_seconds)
        self._init_schema()
        self._restore_window_cursor()

    async def start(self) -> None:
        """Starts the periodic 10-minute anchoring loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop(), name="batch-coordinator")

    async def stop(self) -> None:
        """Stops the coordinator and closes all transport resources."""
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        disconnect = getattr(self._web3.provider, "disconnect", None)
        if disconnect is not None:
            result = disconnect()
            if asyncio.iscoroutine(result):
                await result
        self._pool.close()

    async def record_decision(self, decision_json: dict[str, Any] | str) -> dict[str, Any]:
        """Stores one decision for inclusion in the next Merkle window.

        The canonical leaf format is:
        `assetHash || action(1 byte) || confidence(4 byte uint) || timestamp(8 byte uint)`
        where confidence is scaled by `MERKLE_CONFIDENCE_SCALE`.
        """
        decision = self._parse_decision(decision_json)
        leaf = self._decision_to_leaf(decision)
        await asyncio.to_thread(self._insert_decision_leaf, leaf)
        return {
            "decision_id": leaf.decision_id,
            "status": "queued",
            "leaf_hash": self._hex(leaf.leaf_hash),
            "timestamp": leaf.timestamp,
        }

    async def get_merkle_proof(self, decision_id: str) -> dict[str, Any]:
        """Returns the Merkle proof path for a decision for independent verification."""
        row = await asyncio.to_thread(self._fetch_decision_with_batch, decision_id)
        if row is None:
            raise KeyError(f"Unknown decision_id: {decision_id}")
        if row["batch_id"] is None:
            raise KeyError(f"Decision {decision_id} is not yet included in an anchored batch")

        proof_hashes = await asyncio.to_thread(self._fetch_proof_hashes, row["batch_id"], int(row["leaf_index"]))
        batch_meta = await asyncio.to_thread(self._fetch_batch_meta, row["batch_id"])
        if batch_meta is None:
            raise KeyError(f"Missing batch metadata for decision_id: {decision_id}")

        return {
            "decision_id": decision_id,
            "batch_id": str(row["batch_id"]),
            "merkle_root": self._hex(batch_meta["merkle_root"]),
            "leaf_hash": self._hex(row["leaf_hash"]),
            "proof_hashes": [self._hex(h) for h in proof_hashes],
            "hash_algorithm": batch_meta["hash_algorithm"],
            "leaf_index": int(row["leaf_index"]),
            "window_start": int(batch_meta["window_start"]),
            "window_end": int(batch_meta["window_end"]),
        }

    async def create_dispute(self, asset_hash: str, creator_address: str) -> dict[str, Any]:
        """Creates a dispute record for a decision with on-chain status and Merkle proof."""
        decision_id = self._normalize_decision_id(asset_hash)
        proof = await self.get_merkle_proof(decision_id)
        on_chain_status = await self._fetch_on_chain_decision(decision_id)
        dispute_id = str(uuid.uuid4())
        await asyncio.to_thread(
            self._record_dispute,
            dispute_id,
            decision_id,
            creator_address,
            on_chain_status,
        )
        return {
            "dispute_id": dispute_id,
            "decision_id": decision_id,
            "creator_address": creator_address,
            "status": "initiated",
            "on_chain_status": on_chain_status,
            "merkle_proof": proof,
            "created_at": int(time.time()),
        }

    async def propose_policy(self, policy_id: str, policy_hash: str, valid_from: int) -> dict[str, Any]:
        """Creates a governance policy proposal awaiting signature collection."""
        proposal_id = str(uuid.uuid4())
        nonce = int(time.time() * 1000) % (2**32)
        await asyncio.to_thread(
            self._record_policy_proposal,
            proposal_id,
            policy_id,
            policy_hash,
            valid_from,
            nonce,
        )
        return {
            "proposal_id": proposal_id,
            "policy_id": policy_id,
            "nonce": nonce,
            "status": "pending_signatures",
            "required_signatures": 2,
            "collected_signatures": 0,
            "created_at": int(time.time()),
        }

    async def collect_signature(
        self,
        proposal_id: str,
        signer_address: str,
        signature: str,
    ) -> dict[str, Any]:
        """Collects and validates a signature for a policy proposal."""
        proposal = await asyncio.to_thread(self._fetch_proposal, proposal_id)
        if proposal is None:
            raise KeyError(f"Unknown proposal_id: {proposal_id}")

        sig_bytes = bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)
        if len(sig_bytes) != 65:
            raise ValueError(f"Invalid signature length: {len(sig_bytes)}")

        await asyncio.to_thread(
            self._store_proposal_signature,
            proposal_id,
            signer_address,
            signature,
        )

        collected = await asyncio.to_thread(self._count_proposal_signatures, proposal_id)
        return {
            "proposal_id": proposal_id,
            "signer": signer_address,
            "collected_signatures": collected,
            "required_signatures": 2,
            "ready_to_anchor": collected >= 2,
        }

    async def anchor_policy_on_chain(self, proposal_id: str) -> dict[str, Any]:
        """Anchors a policy proposal on-chain via PolicyRegistry after signature collection."""
        proposal = await asyncio.to_thread(self._fetch_proposal, proposal_id)
        if proposal is None:
            raise KeyError(f"Unknown proposal_id: {proposal_id}")

        signatures = await asyncio.to_thread(self._fetch_proposal_signatures, proposal_id)
        if len(signatures) < 2:
            raise RuntimeError(f"Insufficient signatures: {len(signatures)}/2")

        if self._policy_registry is None:
            raise RuntimeError("POLICY_REGISTRY_CONTRACT is not configured")

        start_time = time.time()
        try:
            sender = AsyncWeb3.to_checksum_address(self._signer.address)
            nonce = await self._web3.eth.get_transaction_count(sender, "pending")
            gas_price = await self._web3.eth.gas_price

            sig_bytes_list = [bytes.fromhex(s[2:] if s.startswith("0x") else s) for s in signatures]
            tx = self._policy_registry.functions.upsertPolicy(
                bytes.fromhex(proposal["policy_id"][2:] if proposal["policy_id"].startswith("0x") else proposal["policy_id"]),
                bytes.fromhex(proposal["policy_hash"][2:] if proposal["policy_hash"].startswith("0x") else proposal["policy_hash"]),
                int(proposal["valid_from"]),
                int(proposal["nonce"]),
                sig_bytes_list,
            ).build_transaction(
                {
                    "chainId": self.config.chain_id,
                    "from": sender,
                    "nonce": nonce,
                    "gasPrice": gas_price,
                }
            )

            tx.setdefault("gas", int((await self._web3.eth.estimate_gas(tx)) * 12 // 10))
            raw_tx = await self._signer.sign_transaction(tx)
            tx_hash = await self._web3.eth.send_raw_transaction(raw_tx)
            gas_used = int(tx["gas"])

            await asyncio.to_thread(self._mark_proposal_anchored, proposal_id, tx_hash.hex())
            BLOCKCHAIN_GAS_USED_TOTAL.labels(action="policy_anchor").inc(gas_used)
            latency = time.time() - start_time
            BLOCKCHAIN_ANCHOR_LATENCY_SECONDS.labels(action="policy_anchor").observe(latency)

            return {
                "proposal_id": proposal_id,
                "tx_hash": tx_hash.hex(),
                "status": "anchored",
                "gas_used": gas_used,
                "latency_seconds": latency,
            }
        except Exception as exc:
            await asyncio.to_thread(self._mark_proposal_anchor_failed, proposal_id, str(exc))
            raise

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._anchor_pending_window()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Batch anchoring cycle failed: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.config.anchor_interval_seconds)
            except TimeoutError:
                continue

    async def _anchor_pending_window(self) -> None:
        window_end = int(time.time())
        window_start = self._window_cursor_unix
        if window_end <= window_start:
            window_end = window_start + int(self.config.anchor_interval_seconds)

        leaves = await asyncio.to_thread(self._load_unbatched_leaves, window_start, window_end)
        if not leaves:
            await asyncio.to_thread(self._store_window_cursor, window_end)
            self._window_cursor_unix = window_end
            return

        batch_id = str(uuid.uuid4())
        merkle_batch, levels, leaf_index_map = self._build_merkle_batch(batch_id=batch_id, leaves=leaves, window_start=window_start, window_end=window_end)
        await asyncio.to_thread(self._persist_batch, merkle_batch, levels, leaves, leaf_index_map)
        await asyncio.to_thread(self._store_window_cursor, window_end)
        self._window_cursor_unix = window_end

        try:
            tx_hash = await self._anchor_batch_on_chain(merkle_batch)
            await asyncio.to_thread(self._mark_batch_anchored, batch_id, tx_hash)
        except Exception as exc:
            await asyncio.to_thread(self._mark_batch_anchor_failed, batch_id, str(exc))
            logger.warning("Merkle batch %s persisted but not anchored on-chain: %s", batch_id, exc)

    def _parse_decision(self, decision_json: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(decision_json, str):
            parsed = json.loads(decision_json)
            if not isinstance(parsed, dict):
                raise ValueError("decision_json string must decode to an object")
            return parsed
        if not isinstance(decision_json, dict):
            raise ValueError("decision_json must be dict or JSON object string")
        return decision_json

    def _decision_to_leaf(self, decision: Mapping[str, Any]) -> DecisionLeaf:
        decision_id = self._decision_id(decision)
        asset_hash = self._normalize_asset_hash(decision)
        action = int(decision.get("action", 0) or 0)
        confidence = float(decision.get("confidence", 0.0) or 0.0)
        timestamp = int(decision.get("timestamp") or time.time())
        canonical_bytes = self._canonical_bytes(asset_hash=asset_hash, action=action, confidence=confidence, timestamp=timestamp)
        leaf_hash = self._hash(canonical_bytes)
        return DecisionLeaf(
            decision_id=decision_id,
            asset_hash=asset_hash,
            action=action,
            confidence=confidence,
            timestamp=timestamp,
            canonical_bytes=canonical_bytes,
            leaf_hash=leaf_hash,
        )

    def _canonical_bytes(self, *, asset_hash: bytes, action: int, confidence: float, timestamp: int) -> bytes:
        action_byte = int(action).to_bytes(1, byteorder="big", signed=False)
        confidence_scaled = int(max(0.0, min(1.0, confidence)) * self.config.min_confidence_scale)
        confidence_bytes = confidence_scaled.to_bytes(4, byteorder="big", signed=False)
        timestamp_bytes = int(timestamp).to_bytes(8, byteorder="big", signed=False)
        return bytes(asset_hash) + action_byte + confidence_bytes + timestamp_bytes

    def _build_merkle_batch(
        self,
        *,
        batch_id: str,
        leaves: list[DecisionLeaf],
        window_start: int,
        window_end: int,
    ) -> tuple[MerkleBatch, list[list[bytes]], dict[str, int]]:
        level_hashes: list[bytes] = [leaf.leaf_hash for leaf in leaves]
        levels: list[list[bytes]] = [level_hashes]
        index_map = {leaf.decision_id: i for i, leaf in enumerate(leaves)}

        current = level_hashes
        while len(current) > 1:
            next_level: list[bytes] = []
            for idx in range(0, len(current), 2):
                left = current[idx]
                right = current[idx + 1] if idx + 1 < len(current) else current[idx]
                next_level.append(self._hash(left + right))
            levels.append(next_level)
            current = next_level

        merkle_root = current[0]
        batch = MerkleBatch(
            batch_id=batch_id,
            window_start=window_start,
            window_end=window_end,
            leaf_count=len(leaves),
            merkle_root=merkle_root,
            manifest_uri=f"{self.config.pending_manifest_prefix}/{batch_id}",
            hash_algorithm=self.config.hash_algorithm,
            created_at=int(time.time()),
        )
        return batch, levels, index_map

    def _insert_decision_leaf(self, leaf: DecisionLeaf) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO merkle_decisions (
                        decision_id, asset_hash, action, confidence_scaled, confidence,
                        decision_timestamp, canonical_bytes, leaf_hash, batch_id, leaf_index, created_at
                    ) VALUES (
                        %(decision_id)s, %(asset_hash)s, %(action)s, %(confidence_scaled)s, %(confidence)s,
                        %(decision_timestamp)s, %(canonical_bytes)s, %(leaf_hash)s, NULL, NULL, NOW()
                    )
                    ON CONFLICT (decision_id) DO NOTHING
                    """,
                    {
                        "decision_id": leaf.decision_id,
                        "asset_hash": psycopg_bytes(leaf.asset_hash),
                        "action": leaf.action,
                        "confidence_scaled": int(max(0.0, min(1.0, leaf.confidence)) * self.config.min_confidence_scale),
                        "confidence": leaf.confidence,
                        "decision_timestamp": leaf.timestamp,
                        "canonical_bytes": psycopg_bytes(leaf.canonical_bytes),
                        "leaf_hash": psycopg_bytes(leaf.leaf_hash),
                    },
                )
            conn.commit()

    def _load_unbatched_leaves(self, window_start: int, window_end: int) -> list[DecisionLeaf]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT decision_id, asset_hash, action, confidence, decision_timestamp, canonical_bytes, leaf_hash
                    FROM merkle_decisions
                    WHERE batch_id IS NULL
                      AND decision_timestamp > %(window_start)s
                      AND decision_timestamp <= %(window_end)s
                    ORDER BY decision_timestamp ASC, decision_id ASC
                    """,
                    {"window_start": window_start, "window_end": window_end},
                )
                rows = cur.fetchall() or []

        leaves: list[DecisionLeaf] = []
        for row in rows:
            leaves.append(
                DecisionLeaf(
                    decision_id=str(row["decision_id"]),
                    asset_hash=bytes(row["asset_hash"]),
                    action=int(row["action"]),
                    confidence=float(row["confidence"]),
                    timestamp=int(row["decision_timestamp"]),
                    canonical_bytes=bytes(row["canonical_bytes"]),
                    leaf_hash=bytes(row["leaf_hash"]),
                )
            )
        return leaves

    def _persist_batch(
        self,
        batch: MerkleBatch,
        levels: list[list[bytes]],
        leaves: list[DecisionLeaf],
        leaf_index_map: dict[str, int],
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO merkle_batches (
                        batch_id, window_start, window_end, leaf_count, merkle_root,
                        manifest_uri, hash_algorithm, status, created_at
                    ) VALUES (
                        %(batch_id)s, %(window_start)s, %(window_end)s, %(leaf_count)s, %(merkle_root)s,
                        %(manifest_uri)s, %(hash_algorithm)s, 'prepared', NOW()
                    )
                    ON CONFLICT (batch_id) DO NOTHING
                    """,
                    {
                        "batch_id": batch.batch_id,
                        "window_start": batch.window_start,
                        "window_end": batch.window_end,
                        "leaf_count": batch.leaf_count,
                        "merkle_root": psycopg_bytes(batch.merkle_root),
                        "manifest_uri": batch.manifest_uri,
                        "hash_algorithm": batch.hash_algorithm,
                    },
                )

                for level, hashes in enumerate(levels):
                    for position, node_hash in enumerate(hashes):
                        is_leaf = level == 0
                        left_hash: bytes | None = None
                        right_hash: bytes | None = None
                        if not is_leaf:
                            prev = levels[level - 1]
                            left_index = position * 2
                            right_index = left_index + 1
                            left_hash = prev[left_index]
                            right_hash = prev[right_index] if right_index < len(prev) else prev[left_index]
                        decision_id = leaves[position].decision_id if is_leaf and position < len(leaves) else None
                        cur.execute(
                            """
                            INSERT INTO merkle_nodes (
                                batch_id, level, position, node_hash, left_hash, right_hash, decision_id, is_leaf
                            ) VALUES (
                                %(batch_id)s, %(level)s, %(position)s, %(node_hash)s, %(left_hash)s, %(right_hash)s, %(decision_id)s, %(is_leaf)s
                            )
                            ON CONFLICT (batch_id, level, position) DO NOTHING
                            """,
                            {
                                "batch_id": batch.batch_id,
                                "level": level,
                                "position": position,
                                "node_hash": psycopg_bytes(node_hash),
                                "left_hash": psycopg_bytes(left_hash) if left_hash is not None else None,
                                "right_hash": psycopg_bytes(right_hash) if right_hash is not None else None,
                                "decision_id": decision_id,
                                "is_leaf": is_leaf,
                            },
                        )

                for decision_id, index in leaf_index_map.items():
                    cur.execute(
                        """
                        UPDATE merkle_decisions
                        SET batch_id = %(batch_id)s,
                            leaf_index = %(leaf_index)s,
                            anchored_at = NOW()
                        WHERE decision_id = %(decision_id)s
                        """,
                        {
                            "batch_id": batch.batch_id,
                            "leaf_index": index,
                            "decision_id": decision_id,
                        },
                    )
            conn.commit()

    async def _anchor_batch_on_chain(self, batch: MerkleBatch) -> str:
        if self._contract is None:
            raise BatchCoordinatorError("MERKLE_ANCHOR_CONTRACT is not configured")

        anchor_fn = getattr(self._contract.functions, "anchorRoot", None) or getattr(self._contract.functions, "anchorBatch")
        sender = AsyncWeb3.to_checksum_address(self._signer.address)
        nonce = await self._web3.eth.get_transaction_count(sender, "pending")
        gas_price = await self._web3.eth.gas_price

        tx = anchor_fn(
            batch.merkle_root,
            int(batch.window_start),
            int(batch.leaf_count),
            batch.manifest_uri,
        ).build_transaction(
            {
                "chainId": self.config.chain_id,
                "from": sender,
                "nonce": nonce,
                "gasPrice": gas_price,
            }
        )

        tx.setdefault("gas", int((await self._web3.eth.estimate_gas(tx)) * 12 // 10))
        raw_tx = await self._signer.sign_transaction(tx)
        tx_hash = await self._web3.eth.send_raw_transaction(raw_tx)
        return tx_hash.hex()

    def _fetch_decision_with_batch(self, decision_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT decision_id, leaf_hash, batch_id, leaf_index
                    FROM merkle_decisions
                    WHERE decision_id = %(decision_id)s
                    """,
                    {"decision_id": decision_id},
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def _fetch_batch_meta(self, batch_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT batch_id, window_start, window_end, merkle_root, hash_algorithm, leaf_count
                    FROM merkle_batches
                    WHERE batch_id = %(batch_id)s
                    """,
                    {"batch_id": batch_id},
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def _fetch_proof_hashes(self, batch_id: str, leaf_index: int) -> list[bytes]:
        proof: list[bytes] = []
        position = leaf_index
        level = 0
        while True:
            sibling_position = position ^ 1
            sibling = self._fetch_node_hash(batch_id=batch_id, level=level, position=sibling_position)
            current = self._fetch_node_hash(batch_id=batch_id, level=level, position=position)
            if sibling is None:
                sibling = current
            proof.append(sibling)

            next_level_hash = self._fetch_node_hash(batch_id=batch_id, level=level + 1, position=position // 2)
            if next_level_hash is None:
                break
            position //= 2
            level += 1
        if proof:
            proof.pop()  # remove root sibling placeholder
        return proof

    def _fetch_node_hash(self, *, batch_id: str, level: int, position: int) -> bytes | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT node_hash
                    FROM merkle_nodes
                    WHERE batch_id = %(batch_id)s
                      AND level = %(level)s
                      AND position = %(position)s
                    """,
                    {"batch_id": batch_id, "level": level, "position": position},
                )
                row = cur.fetchone()
        return bytes(row[0]) if row else None

    def _mark_batch_anchored(self, batch_id: str, tx_hash: str) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE merkle_batches
                    SET status = 'anchored',
                        anchored_tx_hash = %(tx_hash)s,
                        anchored_at = NOW()
                    WHERE batch_id = %(batch_id)s
                    """,
                    {"batch_id": batch_id, "tx_hash": tx_hash},
                )
            conn.commit()

    def _mark_batch_anchor_failed(self, batch_id: str, error: str) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE merkle_batches
                    SET status = 'anchor_failed',
                        last_error = %(error)s
                    WHERE batch_id = %(batch_id)s
                    """,
                    {"batch_id": batch_id, "error": error},
                )
            conn.commit()

    async def _fetch_on_chain_decision(self, decision_id: str) -> dict[str, Any] | None:
        """Fetch decision record from SentinelAudit contract."""
        if self._sentinel_audit is None:
            return None
        try:
            _IPFS_OPERATION_ATTEMPTS.labels(operation="fetch_on_chain_decision").inc()
            decision_id_bytes = bytes.fromhex(decision_id[2:] if decision_id.startswith("0x") else decision_id)
            result = await asyncio.to_thread(
                lambda: self._sentinel_audit.functions.getDecision(decision_id_bytes).call()
            )
            _IPFS_OPERATION_SUCCESSES.labels(operation="fetch_on_chain_decision").inc()
            return {
                "evidence_cid_hash": self._hex(result[0]),
                "gateway": str(result[1]),
                "timestamp": int(result[2]),
                "policy_id": int(result[3]),
                "risk_score_bps": int(result[4]),
                "action": int(result[5]),
                "high_stakes": bool(result[6]),
            }
        except Exception as exc:
            logger.warning("Failed to fetch on-chain decision %s: %s", decision_id, exc)
            return None

    def _record_dispute(
        self,
        dispute_id: str,
        decision_id: str,
        creator_address: str,
        on_chain_status: dict[str, Any] | None,
    ) -> None:
        """Persist dispute record to database."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS disputes (
                        dispute_id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL,
                        creator_address TEXT NOT NULL,
                        on_chain_status JSONB,
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO disputes (dispute_id, decision_id, creator_address, on_chain_status, status)
                    VALUES (%(dispute_id)s, %(decision_id)s, %(creator_address)s, %(on_chain_status)s, 'initiated')
                    ON CONFLICT (dispute_id) DO NOTHING
                    """,
                    {
                        "dispute_id": dispute_id,
                        "decision_id": decision_id,
                        "creator_address": creator_address,
                        "on_chain_status": json.dumps(on_chain_status) if on_chain_status else None,
                    },
                )
            conn.commit()

    def _record_policy_proposal(
        self,
        proposal_id: str,
        policy_id: str,
        policy_hash: str,
        valid_from: int,
        nonce: int,
    ) -> None:
        """Persist policy proposal to database."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS policy_proposals (
                        proposal_id TEXT PRIMARY KEY,
                        policy_id TEXT NOT NULL,
                        policy_hash TEXT NOT NULL,
                        valid_from BIGINT NOT NULL,
                        nonce BIGINT NOT NULL,
                        status TEXT NOT NULL,
                        anchored_tx_hash TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO policy_proposals (proposal_id, policy_id, policy_hash, valid_from, nonce, status)
                    VALUES (%(proposal_id)s, %(policy_id)s, %(policy_hash)s, %(valid_from)s, %(nonce)s, 'pending_signatures')
                    ON CONFLICT (proposal_id) DO NOTHING
                    """,
                    {
                        "proposal_id": proposal_id,
                        "policy_id": policy_id,
                        "policy_hash": policy_hash,
                        "valid_from": valid_from,
                        "nonce": nonce,
                    },
                )
            conn.commit()

    def _store_proposal_signature(self, proposal_id: str, signer: str, signature: str) -> None:
        """Store a signature for a policy proposal."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proposal_signatures (
                        proposal_id TEXT NOT NULL,
                        signer TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        signed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (proposal_id, signer)
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO proposal_signatures (proposal_id, signer, signature)
                    VALUES (%(proposal_id)s, %(signer)s, %(signature)s)
                    ON CONFLICT (proposal_id, signer) DO UPDATE SET signature = %(signature)s
                    """,
                    {"proposal_id": proposal_id, "signer": signer, "signature": signature},
                )
            conn.commit()

    def _fetch_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        """Fetch policy proposal from database."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT proposal_id, policy_id, policy_hash, valid_from, nonce, status FROM policy_proposals WHERE proposal_id = %(proposal_id)s",
                    {"proposal_id": proposal_id},
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def _count_proposal_signatures(self, proposal_id: str) -> int:
        """Count collected signatures for a proposal."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) as cnt FROM proposal_signatures WHERE proposal_id = %(proposal_id)s",
                    {"proposal_id": proposal_id},
                )
                row = cur.fetchone()
        return int(row["cnt"]) if row else 0

    def _fetch_proposal_signatures(self, proposal_id: str) -> list[str]:
        """Fetch up to 3 collected signatures for on-chain anchor."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT signature FROM proposal_signatures WHERE proposal_id = %(proposal_id)s ORDER BY signed_at ASC LIMIT 3",
                    {"proposal_id": proposal_id},
                )
                rows = cur.fetchall() or []
        return [str(row["signature"]) for row in rows]

    def _mark_proposal_anchored(self, proposal_id: str, tx_hash: str) -> None:
        """Mark proposal as successfully anchored on-chain."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE policy_proposals SET status = 'anchored', anchored_tx_hash = %(tx_hash)s WHERE proposal_id = %(proposal_id)s",
                    {"proposal_id": proposal_id, "tx_hash": tx_hash},
                )
            conn.commit()

    def _mark_proposal_anchor_failed(self, proposal_id: str, error: str) -> None:
        """Mark proposal anchor attempt as failed."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE policy_proposals SET status = 'anchor_failed' WHERE proposal_id = %(proposal_id)s",
                    {"proposal_id": proposal_id},
                )
            conn.commit()

    def _normalize_decision_id(self, asset_hash: str) -> str:
        """Ensure decision_id has 0x prefix."""
        if asset_hash.startswith("0x"):
            return asset_hash
        return "0x" + asset_hash

    def _init_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS merkle_decisions (
                decision_id TEXT PRIMARY KEY,
                asset_hash BYTEA NOT NULL,
                action SMALLINT NOT NULL,
                confidence_scaled INTEGER NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                decision_timestamp BIGINT NOT NULL,
                canonical_bytes BYTEA NOT NULL,
                leaf_hash BYTEA NOT NULL,
                batch_id TEXT NULL,
                leaf_index INTEGER NULL,
                anchored_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS merkle_batches (
                batch_id TEXT PRIMARY KEY,
                window_start BIGINT NOT NULL,
                window_end BIGINT NOT NULL,
                leaf_count INTEGER NOT NULL,
                merkle_root BYTEA NOT NULL,
                manifest_uri TEXT NOT NULL,
                hash_algorithm TEXT NOT NULL,
                status TEXT NOT NULL,
                anchored_tx_hash TEXT NULL,
                last_error TEXT NULL,
                anchored_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS merkle_nodes (
                batch_id TEXT NOT NULL,
                level INTEGER NOT NULL,
                position INTEGER NOT NULL,
                node_hash BYTEA NOT NULL,
                left_hash BYTEA NULL,
                right_hash BYTEA NULL,
                decision_id TEXT NULL,
                is_leaf BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (batch_id, level, position)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS merkle_decisions_batch_idx ON merkle_decisions(batch_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS merkle_decisions_timestamp_idx ON merkle_decisions(decision_timestamp)
            """,
            """
            CREATE INDEX IF NOT EXISTS merkle_nodes_decision_idx ON merkle_nodes(decision_id)
            """,
        ]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                for statement in statements:
                    cur.execute(statement)
            conn.commit()

    def _restore_window_cursor(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(window_end) AS window_end FROM merkle_batches"
                )
                row = cur.fetchone()
        if row and row.get("window_end") is not None:
            self._window_cursor_unix = int(row["window_end"])

    def _store_window_cursor(self, window_end: int) -> None:
        self._window_cursor_unix = int(window_end)

    def _decision_id(self, decision: Mapping[str, Any]) -> str:
        value = decision.get("decision_id") or decision.get("id") or decision.get("trace_id")
        if isinstance(value, str) and value:
            return value
        raw = json.dumps(decision, separators=(",", ":"), sort_keys=True, default=self._json_default)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _normalize_asset_hash(self, decision: Mapping[str, Any]) -> bytes:
        raw = decision.get("asset_hash") or decision.get("assetHash") or decision.get("asset_id") or decision.get("assetId")
        if isinstance(raw, bytes) and len(raw) == 32:
            return raw
        if isinstance(raw, str):
            normalized = raw.removeprefix("0x")
            if len(normalized) == 64:
                try:
                    return bytes.fromhex(normalized)
                except ValueError:
                    pass
            return hashlib.sha256(raw.encode("utf-8")).digest()
        return hashlib.sha256(json.dumps(decision, sort_keys=True, default=self._json_default).encode("utf-8")).digest()

    def _hash(self, data: bytes) -> bytes:
        if self.config.hash_algorithm == "keccak256":
            return AsyncWeb3.keccak(data)
        if self.config.hash_algorithm != "sha256":
            raise BatchCoordinatorError(f"Unsupported hash algorithm: {self.config.hash_algorithm}")
        return hashlib.sha256(data).digest()

    @staticmethod
    def _hex(value: bytes) -> str:
        return "0x" + value.hex()

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (set, frozenset, tuple)):
            return list(value)
        if isinstance(value, bytes):
            return value.hex()
        return str(value)
def psycopg_bytes(value: bytes | None) -> bytes | None:
    if value is None:
        return None
    return value

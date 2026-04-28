from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol

import httpx
from prometheus_client import Counter, Gauge
from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider

logger = logging.getLogger(__name__)


_IPFS_UPLOAD_SUCCESSES = Counter(
    "ipfs_upload_successes_total",
    "Total successful IPFS uploads",
)
_IPFS_UPLOAD_ATTEMPTS = Counter(
    "ipfs_upload_attempts_total",
    "Total IPFS upload attempts",
)


_SENTINEL_AUDIT_MIN_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "recordDecision",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "decisionId", "type": "bytes32"},
            {"name": "policyId", "type": "uint64"},
            {"name": "riskScoreBps", "type": "uint32"},
            {"name": "action", "type": "uint8"},
            {"name": "highStakes", "type": "bool"},
            {"name": "evidenceCid", "type": "string"},
        ],
        "outputs": [],
    }
]


class TransactionSigner(Protocol):
    """Abstract transaction signer for local keys and HSM/KMS providers."""

    @property
    def address(self) -> str:
        """Returns the EOA address used as `from` account."""

    async def sign_transaction(self, tx: Mapping[str, Any]) -> bytes:
        """Signs a transaction and returns raw RLP bytes."""


class LocalPrivateKeySigner:
    """Local signer implementation for development/testing environments."""

    def __init__(self, private_key: str) -> None:
        from eth_account import Account

        self._account = Account.from_key(private_key)

    @property
    def address(self) -> str:
        return str(self._account.address)

    async def sign_transaction(self, tx: Mapping[str, Any]) -> bytes:
        signed = self._account.sign_transaction(dict(tx))
        return bytes(signed.raw_transaction)


class HSMCompatibleSigner:
    """Adapter for asynchronous HSM/KMS wallet providers.

    The callback should return raw signed transaction bytes (or hex-encoded string).
    This keeps the service compatible with cloud HSM providers without coupling to one SDK.
    """

    def __init__(self, address: str, signer_callback: Callable[[dict[str, Any]], Any]) -> None:
        self._address = AsyncWeb3.to_checksum_address(address)
        self._callback = signer_callback

    @property
    def address(self) -> str:
        return self._address

    async def sign_transaction(self, tx: Mapping[str, Any]) -> bytes:
        maybe_coroutine = self._callback(dict(tx))
        signed = await maybe_coroutine if asyncio.iscoroutine(maybe_coroutine) else maybe_coroutine
        if isinstance(signed, bytes):
            return signed
        if isinstance(signed, str):
            return bytes.fromhex(signed[2:] if signed.startswith("0x") else signed)
        raise TypeError("HSM signer callback must return bytes or hex string")


@dataclass(frozen=True)
class AuditServiceConfig:
    """Configuration for the Audit Layer blockchain bridge."""

    polygon_rpc_url: str = "http://127.0.0.1:8545"
    sentinel_audit_contract: str = ""
    chain_id: int = 137
    ipfs_api_url: str = "http://127.0.0.1:5001"
    polygon_gas_oracle_url: str = "https://gasstation.polygon.technology/v2"
    max_allowed_gwei: float = 100.0
    gas_poll_interval_seconds: float = 15.0
    queue_scan_interval_seconds: float = 0.2
    retry_base_seconds: float = 1.0
    retry_cap_seconds: float = 120.0
    pending_queue_file: str = "./data/pending_audit_queue.json"
    tx_timeout_seconds: float = 20.0
    ipfs_timeout_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> "AuditServiceConfig":
        return cls(
            polygon_rpc_url=os.getenv("POLYGON_RPC_URL", "http://127.0.0.1:8545"),
            sentinel_audit_contract=os.getenv("SENTINEL_AUDIT_CONTRACT", ""),
            chain_id=int(os.getenv("POLYGON_CHAIN_ID", "137")),
            ipfs_api_url=os.getenv("IPFS_API_URL", "http://127.0.0.1:5001"),
            polygon_gas_oracle_url=os.getenv("POLYGON_GAS_ORACLE_URL", "https://gasstation.polygon.technology/v2"),
            max_allowed_gwei=float(os.getenv("MAX_AUDIT_GAS_GWEI", "100")),
            gas_poll_interval_seconds=float(os.getenv("AUDIT_GAS_POLL_SECONDS", "15")),
            queue_scan_interval_seconds=float(os.getenv("AUDIT_QUEUE_SCAN_SECONDS", "0.2")),
            retry_base_seconds=float(os.getenv("AUDIT_RETRY_BASE_SECONDS", "1.0")),
            retry_cap_seconds=float(os.getenv("AUDIT_RETRY_CAP_SECONDS", "120")),
            pending_queue_file=os.getenv("PENDING_AUDIT_FILE", "./data/pending_audit_queue.json"),
            tx_timeout_seconds=float(os.getenv("AUDIT_TX_TIMEOUT_SECONDS", "20")),
            ipfs_timeout_seconds=float(os.getenv("AUDIT_IPFS_TIMEOUT_SECONDS", "1.0")),
        )


@dataclass
class GasPriceSnapshot:
    """Current gas-price view used for transaction admission control."""

    standard_gwei: float | None = None
    fetched_at_unix: float = field(default_factory=time.time)


class GasPriceManager:
    """Monitors Polygon gas oracle and exposes queue/defer decisions."""

    def __init__(self, config: AuditServiceConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(timeout=5.0)
        self._snapshot = GasPriceSnapshot()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def snapshot(self) -> GasPriceSnapshot:
        return self._snapshot

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="audit-gas-monitor")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        await self._client.aclose()

    def should_defer(self) -> bool:
        if self._snapshot.standard_gwei is None:
            return False
        return self._snapshot.standard_gwei > self._config.max_allowed_gwei

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._snapshot = GasPriceSnapshot(
                    standard_gwei=await self._fetch_polygon_gas_gwei(),
                    fetched_at_unix=time.time(),
                )
            except Exception as exc:
                logger.warning("Gas oracle fetch failed: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._config.gas_poll_interval_seconds)
            except TimeoutError:
                continue

    async def _fetch_polygon_gas_gwei(self) -> float | None:
        response = await self._client.get(self._config.polygon_gas_oracle_url)
        response.raise_for_status()
        payload = response.json()

        candidates: list[float] = []
        if isinstance(payload, dict):
            standard = payload.get("standard")
            if isinstance(standard, dict):
                for key in ("maxFee", "maxPriorityFee", "gasPrice"):
                    val = standard.get(key)
                    if isinstance(val, (int, float)):
                        candidates.append(float(val))
            for root_key in ("fast", "safeLow", "estimatedBaseFee"):
                value = payload.get(root_key)
                if isinstance(value, dict):
                    for k in ("maxFee", "gasPrice"):
                        v = value.get(k)
                        if isinstance(v, (int, float)):
                            candidates.append(float(v))
                elif isinstance(value, (int, float)):
                    candidates.append(float(value))

        return candidates[0] if candidates else None


PendingStage = Literal["ipfs", "tx"]


@dataclass
class PendingAudit:
    """Serialized pending audit item for durable retry processing."""

    queue_id: str
    decision: dict[str, Any]
    evidence_package: dict[str, Any]
    stage: PendingStage
    attempts: int = 0
    next_retry_unix: float = field(default_factory=time.time)
    evidence_cid: str | None = None
    tx_hash: str | None = None
    last_error: str | None = None


class AuditService:
    """Bridge from ML decisions to IPFS + Polygon audit contracts.

    Operational guarantees:
    - `writeAuditRecord` never waits for blockchain confirmation.
    - IPFS/Web3 outages are handled by durable local queue + exponential backoff.
    - High gas periods (above configured threshold) defer transaction submission.
    """

    def __init__(
        self,
        signer: TransactionSigner,
        config: AuditServiceConfig | None = None,
        contract_abi: list[dict[str, Any]] | None = None,
    ) -> None:
        self.config = config or AuditServiceConfig.from_env()
        self._signer = signer
        self._web3 = AsyncWeb3(AsyncHTTPProvider(self.config.polygon_rpc_url))

        if not self.config.sentinel_audit_contract:
            raise ValueError("Missing SENTINEL_AUDIT_CONTRACT / sentinel_audit_contract configuration")

        self._contract = self._web3.eth.contract(
            address=AsyncWeb3.to_checksum_address(self.config.sentinel_audit_contract),
            abi=contract_abi or _SENTINEL_AUDIT_MIN_ABI,
        )
        self._gas_manager = GasPriceManager(self.config)
        self._http = httpx.AsyncClient(timeout=self.config.ipfs_timeout_seconds)

        self._stop = asyncio.Event()
        self._worker_task: asyncio.Task[None] | None = None
        self._queue_lock = asyncio.Lock()
        self._pending: dict[str, PendingAudit] = {}

        self._pending_path = Path(self.config.pending_queue_file)
        self._pending_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_pending_queue()

    async def start(self) -> None:
        """Starts gas monitor and retry worker."""
        await self._gas_manager.start()
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._retry_worker(), name="audit-retry-worker")

    async def stop(self) -> None:
        """Stops background tasks and closes network clients."""
        self._stop.set()
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None
        await self._gas_manager.stop()
        await self._http.aclose()

    async def writeAuditRecord(self, decision_json: dict[str, Any] | str) -> dict[str, Any]:
        """Accepts an ML decision and enqueues audit persistence asynchronously.

        Steps performed:
        1) Parse decision payload.
        2) Assemble IPFS evidence package (`metadata`, `xai_saliency`, `rl_state`).
        3) Queue for IPFS upload.
        4) Queue blockchain transaction once CID is available.

        This method is intentionally non-blocking for Web3/IPFS availability.
        """
        decision = self._parse_decision(decision_json)
        evidence_package = self._assemble_evidence_package(decision)

        queue_id = str(uuid.uuid4())
        item = PendingAudit(
            queue_id=queue_id,
            decision=decision,
            evidence_package=evidence_package,
            stage="ipfs",
            attempts=0,
            next_retry_unix=time.time(),
        )

        async with self._queue_lock:
            self._pending[queue_id] = item
            self._persist_pending_queue_unlocked()

        return {
            "queue_id": queue_id,
            "status": "queued",
            "stage": "ipfs",
            "queued_at": int(time.time()),
        }

    async def get_pending(self) -> list[dict[str, Any]]:
        """Returns the current pending audit queue for observability."""
        async with self._queue_lock:
            return [asdict(item) for item in self._pending.values()]

    def _parse_decision(self, decision_json: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(decision_json, str):
            parsed = json.loads(decision_json)
            if not isinstance(parsed, dict):
                raise ValueError("decision_json string must decode to an object")
            return parsed
        if not isinstance(decision_json, dict):
            raise ValueError("decision_json must be dict or JSON object string")
        return decision_json

    def _assemble_evidence_package(self, decision: Mapping[str, Any]) -> dict[str, Any]:
        metadata = {
            "decision_id": str(decision.get("decision_id") or ""),
            "asset_id": str(decision.get("asset_id") or ""),
            "model_version": decision.get("model_version"),
            "policy_id": int(decision.get("policy_id", 0) or 0),
            "confidence": float(decision.get("confidence", 0.0) or 0.0),
            "risk_score_bps": int(decision.get("risk_score_bps", 0) or 0),
            "action": int(decision.get("action", 0) or 0),
            "high_stakes": bool(decision.get("high_stakes", False)),
            "timestamp": int(time.time()),
            "trace_id": str(decision.get("trace_id") or ""),
        }

        xai_saliency = decision.get("xai_saliency")
        if xai_saliency is None and isinstance(decision.get("xai"), dict):
            xai_saliency = decision["xai"].get("saliency")

        rl_state = decision.get("rl_state") or decision.get("state") or {}

        return {
            "metadata": metadata,
            "xai_saliency": xai_saliency if xai_saliency is not None else {},
            "rl_state": rl_state if isinstance(rl_state, dict) else {"value": rl_state},
            "raw_decision": decision,
        }

    async def _retry_worker(self) -> None:
        while not self._stop.is_set():
            item = await self._get_next_due_item()
            if item is None:
                await asyncio.sleep(self.config.queue_scan_interval_seconds)
                continue

            try:
                if item.stage == "ipfs":
                    item.evidence_cid = await self._upload_evidence_to_ipfs(item.evidence_package)
                    item.stage = "tx"
                    item.attempts = 0
                    item.next_retry_unix = time.time()
                    item.last_error = None
                    await self._upsert_item(item)
                else:
                    if self._gas_manager.should_defer():
                        item.next_retry_unix = time.time() + self.config.gas_poll_interval_seconds
                        item.last_error = (
                            f"Gas too high: {self._gas_manager.snapshot.standard_gwei:.2f} gwei; deferring tx"
                            if self._gas_manager.snapshot.standard_gwei is not None
                            else "Gas unknown; deferring tx"
                        )
                        await self._upsert_item(item)
                        continue

                    tx_hash = await self._submit_audit_transaction(item)
                    item.tx_hash = tx_hash
                    await self._remove_item(item.queue_id)
            except Exception as exc:
                item.attempts += 1
                delay = min(self.config.retry_cap_seconds, self.config.retry_base_seconds * (2 ** max(item.attempts - 1, 0)))
                item.next_retry_unix = time.time() + delay
                item.last_error = str(exc)
                await self._upsert_item(item)
                logger.warning(
                    "Audit item %s failed at stage=%s (attempt=%d). Retrying in %.2fs: %s",
                    item.queue_id,
                    item.stage,
                    item.attempts,
                    delay,
                    exc,
                )

    async def _upload_evidence_to_ipfs(self, evidence_package: Mapping[str, Any]) -> str:
        payload = json.dumps(evidence_package, separators=(",", ":"), default=self._json_default).encode("utf-8")
        files = {"file": ("evidence.json", payload, "application/json")}
        params = {"pin": "true", "cid-version": "1"}

        _IPFS_UPLOAD_ATTEMPTS.inc()
        try:
            response = await self._http.post(f"{self.config.ipfs_api_url}/api/v0/add", files=files, params=params)
            response.raise_for_status()

            # IPFS may return single JSON or newline-delimited JSON.
            text = response.text.strip()
            last_line = text.splitlines()[-1] if text else "{}"
            parsed = json.loads(last_line)
            cid = str(parsed.get("Hash") or "")
            if not cid:
                raise RuntimeError("IPFS add response missing Hash/CID")
            
            _IPFS_UPLOAD_SUCCESSES.inc()
            return cid
        except Exception:
            # Record failure but re-raise for retry handling
            raise

    async def _submit_audit_transaction(self, item: PendingAudit) -> str:
        if not item.evidence_cid:
            raise RuntimeError("Missing evidence CID for on-chain record")

        decision_id = self._decision_id_bytes32(item.decision)
        policy_id = int(item.decision.get("policy_id", 0) or 0)
        risk_score_bps = int(item.decision.get("risk_score_bps") or round(float(item.decision.get("confidence", 0.0) or 0.0) * 10_000))
        action = int(item.decision.get("action", 0) or 0)
        high_stakes = bool(item.decision.get("high_stakes", False))

        data = self._contract.encode_abi(
            "recordDecision",
            args=[decision_id, policy_id, risk_score_bps, action, high_stakes, item.evidence_cid],
        )

        sender = AsyncWeb3.to_checksum_address(self._signer.address)
        nonce = await asyncio.wait_for(
            self._web3.eth.get_transaction_count(sender, "pending"),
            timeout=self.config.tx_timeout_seconds,
        )

        gas_price_wei = await asyncio.wait_for(self._web3.eth.gas_price, timeout=self.config.tx_timeout_seconds)
        oracle_gwei = self._gas_manager.snapshot.standard_gwei
        if oracle_gwei is not None:
            gas_price_wei = int(max(gas_price_wei, AsyncWeb3.to_wei(oracle_gwei, "gwei")))

        estimate = await asyncio.wait_for(
            self._web3.eth.estimate_gas(
                {
                    "from": sender,
                    "to": self._contract.address,
                    "data": data,
                    "value": 0,
                }
            ),
            timeout=self.config.tx_timeout_seconds,
        )

        tx: dict[str, Any] = {
            "chainId": self.config.chain_id,
            "nonce": nonce,
            "to": self._contract.address,
            "data": data,
            "value": 0,
            "gas": int(estimate * 12 // 10),
            "maxFeePerGas": int(gas_price_wei),
            "maxPriorityFeePerGas": int(min(gas_price_wei, AsyncWeb3.to_wei(5, "gwei"))),
            "type": 2,
        }

        raw_tx = await self._signer.sign_transaction(tx)
        tx_hash = await asyncio.wait_for(self._web3.eth.send_raw_transaction(raw_tx), timeout=self.config.tx_timeout_seconds)
        return tx_hash.hex()

    def _decision_id_bytes32(self, decision: Mapping[str, Any]) -> bytes:
        existing = decision.get("decision_id")
        if isinstance(existing, str) and existing.startswith("0x") and len(existing) == 66:
            return bytes.fromhex(existing[2:])
        if isinstance(existing, str) and len(existing) == 64:
            return bytes.fromhex(existing)

        canonical = json.dumps(decision, separators=(",", ":"), sort_keys=True, default=self._json_default)
        return AsyncWeb3.keccak(text=canonical)

    async def _get_next_due_item(self) -> PendingAudit | None:
        now = time.time()
        async with self._queue_lock:
            due = [item for item in self._pending.values() if item.next_retry_unix <= now]
            if not due:
                return None
            due.sort(key=lambda item: (item.next_retry_unix, item.attempts))
            return due[0]

    async def _upsert_item(self, item: PendingAudit) -> None:
        async with self._queue_lock:
            self._pending[item.queue_id] = item
            self._persist_pending_queue_unlocked()

    async def _remove_item(self, queue_id: str) -> None:
        async with self._queue_lock:
            self._pending.pop(queue_id, None)
            self._persist_pending_queue_unlocked()

    def _load_pending_queue(self) -> None:
        if not self._pending_path.exists():
            return
        try:
            parsed = json.loads(self._pending_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, list):
                return
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                try:
                    item = PendingAudit(**entry)
                    self._pending[item.queue_id] = item
                except TypeError:
                    continue
        except Exception as exc:
            logger.warning("Failed to load pending audit queue from %s: %s", self._pending_path, exc)

    def _persist_pending_queue_unlocked(self) -> None:
        tmp = self._pending_path.with_suffix(self._pending_path.suffix + ".tmp")
        payload = [asdict(item) for item in self._pending.values()]
        tmp.write_text(json.dumps(payload, separators=(",", ":"), default=self._json_default), encoding="utf-8")
        tmp.replace(self._pending_path)

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (set, frozenset, tuple)):
            return list(value)
        if isinstance(value, bytes):
            return value.hex()
        return str(value)

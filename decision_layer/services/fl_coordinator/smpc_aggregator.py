from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from prometheus_client import Gauge


SCALE_BITS = 16
SCALE_FACTOR = 1 << SCALE_BITS
DEFAULT_PRIME = 2_305_843_009_213_693_951  # 2^61-1 (Mersenne prime)


class SMPCError(RuntimeError):
    """Base error for SMPC aggregation failures."""


class SMPCOverflowError(SMPCError):
    """Raised when fixed-point conversion or reconstruction overflows the modulus budget."""


class NodeDropoutError(SMPCError):
    """Raised when insufficient participant updates are available for secure aggregation."""


@dataclass(frozen=True)
class SMPCConfig:
    """Configuration for additive secret-sharing aggregation."""

    parties: int = 3
    prime_modulus: int = DEFAULT_PRIME
    min_clients: int = 2
    scale_factor: int = SCALE_FACTOR


class AdditiveSMPCAggregator:
    """Asynchronous additive-secret-sharing aggregator with fixed-point arithmetic.

    Float tensors are encoded as signed fixed-point integers then mapped into
    $
    \mathbb{Z}_P
    $ with additive shares. Three virtual parties sum shares in parallel,
    and the reconstruction party decodes the secure sum back to floating-point.
    """

    def __init__(self, config: SMPCConfig | None = None) -> None:
        self.config = config or SMPCConfig()
        self.reconstruction_errors_gauge = Gauge(
            "smpc_reconstruction_errors",
            "Total SMPC reconstruction failures observed by the coordinator",
        )

    @property
    def _half_modulus(self) -> int:
        return self.config.prime_modulus // 2

    def _encode_fixed(self, values: np.ndarray) -> np.ndarray:
        scaled = np.rint(values.astype(np.float64) * float(self.config.scale_factor))
        max_safe = self._half_modulus - 1
        if np.any(np.abs(scaled) > max_safe):
            raise SMPCOverflowError(
                f"Fixed-point overflow: |value*scale| exceeded {max_safe} before modular projection"
            )

        encoded = scaled.astype(np.int64)
        return np.mod(encoded, self.config.prime_modulus).astype(np.int64)

    def _decode_fixed(self, modular_values: np.ndarray) -> np.ndarray:
        signed = modular_values.astype(np.int64).copy()
        gt_half = signed > self._half_modulus
        signed[gt_half] = signed[gt_half] - self.config.prime_modulus

        if np.any(np.abs(signed.astype(np.float64)) > self._half_modulus):
            raise SMPCOverflowError("Reconstruction overflow detected after sign recovery")

        return (signed.astype(np.float64) / float(self.config.scale_factor)).astype(np.float32)

    def _split_into_shares(self, encoded: np.ndarray) -> list[np.ndarray]:
        shares: list[np.ndarray] = []
        running = np.zeros_like(encoded, dtype=np.int64)

        for _ in range(self.config.parties - 1):
            random_share = np.fromiter(
                (secrets.randbelow(self.config.prime_modulus) for _ in range(encoded.size)),
                dtype=np.int64,
                count=encoded.size,
            ).reshape(encoded.shape)
            shares.append(random_share)
            running = (running + random_share) % self.config.prime_modulus

        final_share = (encoded - running) % self.config.prime_modulus
        shares.append(final_share.astype(np.int64))
        return shares

    async def _party_sum(self, party_id: int, party_shares: Sequence[np.ndarray]) -> np.ndarray:
        if len(party_shares) == 0:
            raise NodeDropoutError(f"Party {party_id} received no shares (all clients dropped out)")

        await asyncio.sleep(0)
        total = np.zeros_like(party_shares[0], dtype=np.int64)
        for share in party_shares:
            total = (total + share) % self.config.prime_modulus
        return total

    async def secure_sum(self, client_tensors: Sequence[np.ndarray]) -> np.ndarray:
        """Securely sum a list of client tensors.

        Raises:
            NodeDropoutError: If participant count is below `min_clients`.
            SMPCOverflowError: On fixed-point encoding/decoding overflow.
            SMPCError: On malformed input shape mismatch.
        """
        if len(client_tensors) < self.config.min_clients:
            raise NodeDropoutError(
                f"Insufficient client updates for secure aggregation: {len(client_tensors)} < {self.config.min_clients}"
            )

        reference_shape = client_tensors[0].shape
        for idx, tensor in enumerate(client_tensors):
            if tensor.shape != reference_shape:
                raise SMPCError(
                    f"Client tensor shape mismatch at index {idx}: expected {reference_shape}, got {tensor.shape}"
                )

        shares_by_party: list[list[np.ndarray]] = [[] for _ in range(self.config.parties)]
        for tensor in client_tensors:
            encoded = self._encode_fixed(np.asarray(tensor, dtype=np.float32))
            shares = self._split_into_shares(encoded)
            for party_idx, share in enumerate(shares):
                shares_by_party[party_idx].append(share)

        tasks = [
            asyncio.create_task(self._party_sum(party_id=party_idx, party_shares=shares_by_party[party_idx]))
            for party_idx in range(self.config.parties)
        ]

        try:
            partial_sums = await asyncio.gather(*tasks)
            reconstructed_mod = np.zeros_like(partial_sums[0], dtype=np.int64)
            for part in partial_sums:
                reconstructed_mod = (reconstructed_mod + part) % self.config.prime_modulus
            return self._decode_fixed(reconstructed_mod)
        except Exception:
            self.reconstruction_errors_gauge.inc()
            raise

    async def secure_average(self, client_tensors: Sequence[np.ndarray]) -> np.ndarray:
        """Securely compute average tensor from client tensors."""
        secure_sum_tensor = await self.secure_sum(client_tensors)
        return (secure_sum_tensor / float(len(client_tensors))).astype(np.float32)

from __future__ import annotations

import json
import logging
import os
from typing import Any

import flwr as fl
import numpy as np
import redis  # type: ignore[reportMissingImports]

try:
    from decision_layer.services.fl_coordinator.strategy import SMPCFedAvg  # type: ignore[reportMissingImports]
    from decision_layer.services.fl_edge.client import client_factory  # type: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    from services.fl_coordinator.strategy import SMPCFedAvg  # type: ignore[reportMissingImports]
    from services.fl_edge.client import client_factory  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)


def _synthetic_samples(total_samples: int = 50, in_features: int = 32) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed=42)
    samples: list[dict[str, Any]] = []
    for idx in range(total_samples):
        features = rng.normal(0.0, 1.0, size=(in_features,)).astype(np.float32).tolist()
        label = int((sum(features[:4]) + rng.normal(0, 0.1)) > 0)
        samples.append({"sample_id": idx + 1, "features": features, "label": label})
    return samples


def _load_round_samples() -> list[dict[str, Any]]:
    r = _redis_client()
    active_round = r.get("fl:active_round_id")
    if not active_round:
        return _synthetic_samples(total_samples=50, in_features=int(os.getenv("FL_IN_FEATURES", "32")))

    payload = r.get(f"fl:round:samples:{active_round}")
    if not payload:
        return _synthetic_samples(total_samples=50, in_features=int(os.getenv("FL_IN_FEATURES", "32")))

    try:
        samples = json.loads(payload)
        if not isinstance(samples, list):
            raise ValueError("Round payload is not a list")
        return [dict(s) for s in samples]
    except Exception:
        return _synthetic_samples(total_samples=50, in_features=int(os.getenv("FL_IN_FEATURES", "32")))


def _disjoint_shards(samples: list[dict[str, Any]], num_nodes: int = 5, shard_size: int = 10) -> list[list[dict[str, Any]]]:
    """Create disjoint shards (node-1:1-10, node-2:11-20, ...)."""
    normalized = sorted(samples, key=lambda x: int(x.get("sample_id", 0) or 0))
    required = num_nodes * shard_size

    if len(normalized) < required:
        normalized.extend(_synthetic_samples(total_samples=required - len(normalized), in_features=int(os.getenv("FL_IN_FEATURES", "32"))))

    normalized = normalized[:required]
    shards: list[list[dict[str, Any]]] = []
    for node_idx in range(num_nodes):
        start = node_idx * shard_size
        end = start + shard_size
        shards.append(normalized[start:end])
    return shards


def run_simulation(num_rounds: int = 3) -> None:
    """Run 5-node Flower simulation on Ray backend with custom SMPC strategy."""
    all_samples = _load_round_samples()
    shards = _disjoint_shards(all_samples, num_nodes=5, shard_size=10)

    def client_fn(cid: str) -> fl.client.Client:
        client_idx = int(cid)
        node_id = f"node-{client_idx + 1}"
        return client_factory(node_id=node_id, shard_samples=shards[client_idx]).to_client()

    strategy = SMPCFedAvg(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=5,
        min_evaluate_clients=5,
        min_available_clients=5,
        accept_failures=True,
    )

    fl.simulation.start_simulation(
        client_fn=client_fn,
        num_clients=5,
        config=fl.server.ServerConfig(num_rounds=num_rounds),
        strategy=strategy,
        client_resources={"num_cpus": 1},
        ray_init_args={
            "include_dashboard": False,
            "ignore_reinit_error": True,
            "log_to_driver": False,
        },
    )


def main() -> None:
    rounds = int(os.getenv("FL_SIM_ROUNDS", "3"))
    run_simulation(num_rounds=rounds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

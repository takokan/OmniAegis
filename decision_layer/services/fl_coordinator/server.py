from __future__ import annotations

import logging
import os
import threading
from typing import Any

import flwr as fl

try:
    from decision_layer.services.fl_coordinator.round_monitor import RoundMonitor  # type: ignore[reportMissingImports]
    from decision_layer.services.fl_coordinator.strategy import SMPCFedAvg  # type: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    from services.fl_coordinator.round_monitor import RoundMonitor  # type: ignore[reportMissingImports]
    from services.fl_coordinator.strategy import SMPCFedAvg  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


def build_strategy() -> SMPCFedAvg:
    """Build production strategy with conservative defaults for 5-node simulation."""
    return SMPCFedAvg(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=5,
        min_evaluate_clients=5,
        min_available_clients=5,
        accept_failures=True,
    )


def start_fl_server(
    server_address: str = "0.0.0.0:8080",
    num_rounds: int = 3,
    with_round_monitor: bool = True,
) -> None:
    """Start Flower gRPC coordinator server and optional Redis round monitor."""
    strategy = build_strategy()

    if with_round_monitor:
        monitor = RoundMonitor()
        monitor_thread = threading.Thread(target=monitor.run_forever, name="fl-round-monitor", daemon=True)
        monitor_thread.start()
        logger.info("Round monitor started (daemon thread)")

    logger.info("Starting Flower coordinator on %s for %d rounds", server_address, num_rounds)
    fl.server.start_server(
        server_address=server_address,
        config=fl.server.ServerConfig(num_rounds=num_rounds),
        strategy=strategy,
    )


def main() -> None:
    """Entrypoint used by deployment scripts and local testing."""
    address = os.getenv("FL_SERVER_ADDRESS", "0.0.0.0:8080")
    rounds = int(os.getenv("FL_SERVER_ROUNDS", "3"))
    with_monitor = os.getenv("FL_ENABLE_ROUND_MONITOR", "1").strip() in {"1", "true", "True"}
    start_fl_server(server_address=address, num_rounds=rounds, with_round_monitor=with_monitor)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

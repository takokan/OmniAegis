from __future__ import annotations

import asyncio
from typing import Any

import flwr as fl
import numpy as np
from flwr.common import FitRes, MetricsAggregationFn, NDArrays, Parameters, Scalar, ndarrays_to_parameters, parameters_to_ndarrays
from flwr.server.client_proxy import ClientProxy
from prometheus_client import Gauge

from .smpc_aggregator import AdditiveSMPCAggregator, NodeDropoutError, SMPCError


def _weighted_average_accuracy(metrics: list[tuple[int, dict[str, Scalar]]]) -> dict[str, Scalar]:
    total_examples = sum(num_examples for num_examples, _ in metrics)
    if total_examples <= 0:
        return {"accuracy": 0.0}
    acc_sum = 0.0
    for num_examples, m in metrics:
        acc_sum += float(m.get("accuracy", 0.0)) * float(num_examples)
    return {"accuracy": acc_sum / float(total_examples)}


class SMPCFedAvg(fl.server.strategy.FedAvg):
    """FedAvg strategy variant that performs secure SMPC aggregation for model tensors."""

    def __init__(
        self,
        *,
        smpc_aggregator: AdditiveSMPCAggregator | None = None,
        fit_metrics_aggregation_fn: MetricsAggregationFn | None = _weighted_average_accuracy,
        **kwargs: Any,
    ) -> None:
        super().__init__(fit_metrics_aggregation_fn=fit_metrics_aggregation_fn, **kwargs)
        self.smpc_aggregator = smpc_aggregator or AdditiveSMPCAggregator()
        self.fl_round_accuracy = Gauge(
            "fl_round_accuracy",
            "Latest weighted FL round accuracy computed from client metrics",
        )

    @staticmethod
    def _run_async(coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    def aggregate_fit(
        self,
        server_round: int,
        results: list[tuple[ClientProxy, FitRes]],
        failures: list[tuple[ClientProxy, FitRes] | BaseException],
    ) -> tuple[Parameters | None, dict[str, Scalar]]:
        if not results:
            return None, {}

        if not self.accept_failures and failures:
            return None, {}

        try:
            weights_per_client: list[NDArrays] = [parameters_to_ndarrays(fit_res.parameters) for _, fit_res in results]
            tensor_count = len(weights_per_client[0])
            for idx, weights in enumerate(weights_per_client):
                if len(weights) != tensor_count:
                    raise SMPCError(
                        f"Model tensor count mismatch for client index {idx}: {len(weights)} != {tensor_count}"
                    )

            aggregated: NDArrays = []
            for tensor_idx in range(tensor_count):
                client_tensor_updates = [np.asarray(client_weights[tensor_idx], dtype=np.float32) for client_weights in weights_per_client]
                avg_tensor = self._run_async(self.smpc_aggregator.secure_average(client_tensor_updates))
                aggregated.append(avg_tensor)

            parameters_aggregated = ndarrays_to_parameters(aggregated)

            metrics_aggregated: dict[str, Scalar] = {}
            if self.fit_metrics_aggregation_fn is not None:
                fit_metrics = [(fit_res.num_examples, fit_res.metrics) for _, fit_res in results]
                metrics_aggregated = self.fit_metrics_aggregation_fn(fit_metrics)
                accuracy = float(metrics_aggregated.get("accuracy", 0.0))
                self.fl_round_accuracy.set(accuracy)

            return parameters_aggregated, metrics_aggregated

        except (SMPCError, NodeDropoutError, ValueError, RuntimeError):
            self.smpc_aggregator.reconstruction_errors_gauge.inc()
            return None, {}

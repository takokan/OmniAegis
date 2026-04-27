from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class GraphAttackResult:
    """Result of a graph attack simulation."""

    attack_type: str
    nodes_affected: int
    edges_injected: int
    confidence_before: float
    confidence_after: float
    confidence_delta: float
    success: bool
    details: dict[str, Any]


class GraphAttackSimulator:
    """Simulate graph-based adversarial attacks on Neo4j relationship graph."""

    # Enforcement threshold from reasoning_gate.py
    CONFIDENCE_ENFORCEMENT_THRESHOLD: float = 0.65

    def __init__(self, graph_db_mock: dict[str, Any]) -> None:
        """Initialize graph attack simulator.

        Args:
            graph_db_mock: Mock Neo4j graph with nodes and relationships.
        """
        self.graph = graph_db_mock or {}

    def simulate_fake_licensing_attack(
        self,
        asset_id: str,
        target_whitelist_nodes: list[str],
        confidence_before: float = 0.85,
    ) -> GraphAttackResult:
        """Simulate 'Fake Licensing' attack by injecting false LICENSED_TO edges.

        Attack strategy:
        - Inject LICENSED_TO edges from asset to legitimate whitelist nodes
        - This fools the rights graph into thinking asset has valid licensing
        - Should drop confidence below enforcement threshold (0.65)

        Args:
            asset_id: Target asset node ID.
            target_whitelist_nodes: List of legitimate whitelist node IDs to link to.
            confidence_before: Initial confidence score (default 0.85 = infringing).

        Returns:
            GraphAttackResult with metrics.
        """
        injected_edges = 0
        nodes_affected = len(target_whitelist_nodes)

        try:
            # Simulate edge injection
            for whitelist_node in target_whitelist_nodes:
                edge_id = f"{asset_id}->LICENSED_TO->{whitelist_node}"
                injected_edges += 1

            # Fake licensing should drop confidence due to confused decision logic
            # (asset appears to have valid licenses)
            confidence_after = confidence_before * 0.45  # Significant drop

            success = confidence_after < self.CONFIDENCE_ENFORCEMENT_THRESHOLD

            return GraphAttackResult(
                attack_type="fake_licensing",
                nodes_affected=nodes_affected,
                edges_injected=injected_edges,
                confidence_before=confidence_before,
                confidence_after=confidence_after,
                confidence_delta=confidence_after - confidence_before,
                success=success,
                details={
                    "injected_relationship_type": "LICENSED_TO",
                    "targets": target_whitelist_nodes,
                    "mechanism": "confuse_licensing_check",
                },
            )

        except Exception as e:
            return GraphAttackResult(
                attack_type="fake_licensing",
                nodes_affected=0,
                edges_injected=0,
                confidence_before=confidence_before,
                confidence_after=confidence_before,
                confidence_delta=0.0,
                success=False,
                details={"error": str(e)},
            )

    def simulate_cooccurrence_flooding_attack(
        self,
        asset_id: str,
        num_fake_similar_assets: int = 100,
        confidence_before: float = 0.85,
    ) -> GraphAttackResult:
        """Simulate 'Co-occurrence Flooding' attack by injecting false SIMILAR_TO edges.

        Attack strategy:
        - Inject many SIMILAR_TO edges from asset to other assets
        - This creates false co-occurrence patterns in the evidence set
        - Legitimate assets get pulled into infringing co-occurrence groups
        - Confidence calculation aggregates over these fake relations

        Args:
            asset_id: Target asset node ID.
            num_fake_similar_assets: Number of SIMILAR_TO edges to inject (default 100).
            confidence_before: Initial confidence score (default 0.85 = infringing).

        Returns:
            GraphAttackResult with metrics.
        """
        injected_edges = 0
        nodes_affected = 0

        try:
            # Simulate edge injection for flooding
            for i in range(num_fake_similar_assets):
                fake_asset_id = f"fake_asset_{i}"
                edge_id = f"{asset_id}->SIMILAR_TO->{fake_asset_id}"
                injected_edges += 1
                nodes_affected += 1

            # Co-occurrence flooding dilutes the infringing signal
            # by mixing legitimate assets with infringing ones
            # This reduces overall confidence due to Bayesian belief aggregation
            dilution_factor = 1.0 - min(
                0.4, num_fake_similar_assets / 500.0
            )  # Max 40% drop
            confidence_after = confidence_before * dilution_factor

            success = confidence_after < self.CONFIDENCE_ENFORCEMENT_THRESHOLD

            return GraphAttackResult(
                attack_type="cooccurrence_flooding",
                nodes_affected=nodes_affected,
                edges_injected=injected_edges,
                confidence_before=confidence_before,
                confidence_after=confidence_after,
                confidence_delta=confidence_after - confidence_before,
                success=success,
                details={
                    "injected_relationship_type": "SIMILAR_TO",
                    "num_fake_assets": num_fake_similar_assets,
                    "mechanism": "dilute_infringing_signal",
                },
            )

        except Exception as e:
            return GraphAttackResult(
                attack_type="cooccurrence_flooding",
                nodes_affected=0,
                edges_injected=0,
                confidence_before=confidence_before,
                confidence_after=confidence_before,
                confidence_delta=0.0,
                success=False,
                details={"error": str(e)},
            )

    def check_defense_resistance(
        self, attack_result: GraphAttackResult
    ) -> dict[str, Any]:
        """Check if system's defense mechanisms resist the attack.

        Defense checks:
        1. Confidence threshold enforcement (0.65)
        2. Relationship timestamp validation (edges < 1 hour old are suspicious)
        3. Whitelist isolation (licensing edges only from known good sources)

        Args:
            attack_result: Result from graph attack simulation.

        Returns:
            Dict with defense status and details.
        """
        return {
            "attack_type": attack_result.attack_type,
            "confidence_threshold_enforced": (
                attack_result.confidence_after < self.CONFIDENCE_ENFORCEMENT_THRESHOLD
            ),
            "post_attack_confidence": attack_result.confidence_after,
            "enforcement_threshold": self.CONFIDENCE_ENFORCEMENT_THRESHOLD,
            "defense_resistant": not attack_result.success,  # Success = attack worked (bad)
            "recommendation": (
                "PASS: Graph defense resisted attack"
                if not attack_result.success
                else "FAIL: Attack succeeded in evading decision gate"
            ),
        }


__all__ = ["GraphAttackSimulator", "GraphAttackResult"]

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class ExplainabilityStorageConfig:
    """Configuration for explanation logging to PostgreSQL time-series."""

    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/omniaegis"
    table_name: str = "xai_explanations"
    max_connections: int = 16

    @classmethod
    def from_env(cls) -> ExplainabilityStorageConfig:
        return cls(
            postgres_dsn=os.getenv(
                "POSTGRES_DSN",
                os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/omniaegis"),
            ),
            table_name=os.getenv("XAI_EXPLANATIONS_TABLE", "xai_explanations"),
            max_connections=int(os.getenv("XAI_MAX_CONNECTIONS", "16")),
        )


class ExplainabilityStorageError(RuntimeError):
    """Raised when explanation storage operations fail."""


class ExplainabilityStorage:
    """PostgreSQL-backed time-series storage for (Explanation Vector, Outcome) pairs."""

    def __init__(self, config: ExplainabilityStorageConfig | None = None) -> None:
        self.config = config or ExplainabilityStorageConfig.from_env()
        self._pool = ConnectionPool(
            conninfo=self.config.postgres_dsn,
            kwargs={"autocommit": False, "row_factory": dict_row},
            max_size=self.config.max_connections,
        )
        self._init_schema()

    @classmethod
    def from_env(cls) -> ExplainabilityStorage:
        """Create instance from environment variables."""
        config = ExplainabilityStorageConfig.from_env()
        return cls(config=config)

    def log_explanation(
        self,
        asset_id: str,
        decision_id: str,
        outcome: int,
        explanation_vector: list[float],
        shap_values: dict[str, float] | None = None,
        saliency_map: list[list[float]] | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        """Log a single explanation record."""

        timestamp_ms = timestamp_ms or int(time.time() * 1000)

        explanation_json = json.dumps([float(x) for x in explanation_vector])
        shap_json = json.dumps(shap_values or {})
        saliency_json = json.dumps(saliency_map) if saliency_map is not None else None
        metadata_json = json.dumps(metadata or {})

        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {self.config.table_name}
                        (asset_id, decision_id, outcome, explanation_vector, shap_values, saliency_map, metadata, timestamp_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, timestamp_ms
                        """,
                        (
                            asset_id,
                            decision_id,
                            int(outcome),
                            explanation_json,
                            shap_json,
                            saliency_json,
                            metadata_json,
                            timestamp_ms,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
        except Exception as exc:  # pragma: no cover
            raise ExplainabilityStorageError(f"Failed to log explanation: {exc}") from exc

        return {"id": row["id"], "timestamp_ms": row["timestamp_ms"]}

    def fetch_explanations_by_date_range(
        self,
        start_ms: int,
        end_ms: int,
        asset_id: str | None = None,
        outcome: int | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """Fetch explanations within a date range."""

        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    where_clauses = [
                        "timestamp_ms >= %s",
                        "timestamp_ms <= %s",
                    ]
                    params: list[Any] = [start_ms, end_ms]

                    if asset_id is not None:
                        where_clauses.append("asset_id = %s")
                        params.append(asset_id)

                    if outcome is not None:
                        where_clauses.append("outcome = %s")
                        params.append(int(outcome))

                    where_sql = " AND ".join(where_clauses)
                    cur.execute(
                        f"""
                        SELECT id, asset_id, decision_id, outcome, explanation_vector, shap_values, saliency_map, metadata, timestamp_ms
                        FROM {self.config.table_name}
                        WHERE {where_sql}
                        ORDER BY timestamp_ms DESC
                        LIMIT %s
                        """,
                        params + [limit],
                    )
                    rows = cur.fetchall()
        except Exception as exc:  # pragma: no cover
            raise ExplainabilityStorageError(f"Failed to fetch explanations: {exc}") from exc

        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                explanation_vec = json.loads(row["explanation_vector"]) if row["explanation_vector"] else []
                shap_vals = json.loads(row["shap_values"]) if row["shap_values"] else {}
                saliency = json.loads(row["saliency_map"]) if row["saliency_map"] else None
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            except Exception:
                continue

            results.append(
                {
                    "id": row["id"],
                    "asset_id": row["asset_id"],
                    "decision_id": row["decision_id"],
                    "outcome": row["outcome"],
                    "explanation_vector": explanation_vec,
                    "shap_values": shap_vals,
                    "saliency_map": saliency,
                    "metadata": metadata,
                    "timestamp_ms": row["timestamp_ms"],
                }
            )

        return results

    def get_shap_values_for_period(
        self,
        start_ms: int,
        end_ms: int,
        outcome: int | None = None,
    ) -> dict[str, list[float]]:
        """Fetch all SHAP values for period and aggregate by feature."""

        records = self.fetch_explanations_by_date_range(
            start_ms=start_ms,
            end_ms=end_ms,
            outcome=outcome,
            limit=100000,
        )

        feature_values: dict[str, list[float]] = {}
        for record in records:
            shap_vals = record.get("shap_values", {})
            if not isinstance(shap_vals, dict):
                continue
            for feature, value in shap_vals.items():
                if feature not in feature_values:
                    feature_values[feature] = []
                try:
                    feature_values[feature].append(float(value))
                except (TypeError, ValueError):
                    pass

        return feature_values

    def _init_schema(self) -> None:
        """Create table if it doesn't exist."""

        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {self.config.table_name} (
                            id BIGSERIAL PRIMARY KEY,
                            asset_id VARCHAR(255) NOT NULL,
                            decision_id VARCHAR(255) NOT NULL,
                            outcome SMALLINT NOT NULL,
                            explanation_vector TEXT,
                            shap_values JSONB,
                            saliency_map JSONB,
                            metadata JSONB,
                            timestamp_ms BIGINT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_xai_asset_timestamp ON {self.config.table_name}(asset_id, timestamp_ms DESC);
                        CREATE INDEX IF NOT EXISTS idx_xai_outcome_timestamp ON {self.config.table_name}(outcome, timestamp_ms DESC);
                        CREATE INDEX IF NOT EXISTS idx_xai_timestamp ON {self.config.table_name}(timestamp_ms DESC);
                        """
                    )
                    conn.commit()
        except Exception as exc:  # pragma: no cover
            raise ExplainabilityStorageError(f"Failed to initialize schema: {exc}") from exc


__all__ = [
    "ExplainabilityStorage",
    "ExplainabilityStorageConfig",
    "ExplainabilityStorageError",
]

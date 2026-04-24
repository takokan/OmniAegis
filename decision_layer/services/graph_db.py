from __future__ import annotations

import os
from typing import Any

from neo4j import GraphDatabase


class GraphDBService:
    """Neo4j wrapper with connection pooling and lightweight helpers."""

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_connection_pool_size: int = 20,
    ) -> None:
        self.uri = uri
        self.database = database
        self.driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=max_connection_pool_size,
        )

    @classmethod
    def from_env(cls) -> GraphDBService:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "neo4j")
        database = os.getenv("NEO4J_DATABASE", "neo4j")
        pool_size = int(os.getenv("NEO4J_POOL_SIZE", "20"))
        return cls(uri=uri, user=user, password=password, database=database, max_connection_pool_size=pool_size)

    def close(self) -> None:
        self.driver.close()

    def run_migrations(self) -> None:
        queries = [
            "CREATE CONSTRAINT asset_id_unique IF NOT EXISTS FOR (a:Asset) REQUIRE a.asset_id IS UNIQUE",
            "CREATE CONSTRAINT creator_id_unique IF NOT EXISTS FOR (c:Creator) REQUIRE c.creator_id IS UNIQUE",
            "CREATE CONSTRAINT licensee_id_unique IF NOT EXISTS FOR (l:Licensee) REQUIRE l.licensee_id IS UNIQUE",
            "CREATE INDEX asset_modality_idx IF NOT EXISTS FOR (a:Asset) ON (a.modality)",
        ]
        with self.driver.session(database=self.database) as session:
            for q in queries:
                session.run(q)

    def upsert_asset_context(
        self,
        asset_id: str,
        metadata: dict[str, Any],
        neighbors: list[dict[str, Any]] | None = None,
    ) -> None:
        neighbors = neighbors or []
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (a:Asset {asset_id: $asset_id})
                SET a.modality = $modality,
                    a.source = $source,
                    a.filename = $filename,
                    a.is_flagged = $is_flagged
                """,
                asset_id=asset_id,
                modality=metadata.get("modality"),
                source=metadata.get("source"),
                filename=metadata.get("filename"),
                is_flagged=bool(metadata.get("is_flagged", False)),
            )

            creator_id = metadata.get("creator_id")
            if creator_id:
                session.run(
                    """
                    MERGE (c:Creator {creator_id: $creator_id})
                    SET c.trust_score = $trust_score,
                        c.tenure_months = $tenure_months,
                        c.verified = $verified
                    WITH c
                    MATCH (a:Asset {asset_id: $asset_id})
                    MERGE (a)-[:CREATED_BY]->(c)
                    """,
                    asset_id=asset_id,
                    creator_id=str(creator_id),
                    trust_score=float(metadata.get("creator_trust_score", 0.5)),
                    tenure_months=float(metadata.get("creator_tenure_months", 12.0)),
                    verified=bool(metadata.get("creator_verified", False)),
                )

            licensee_id = metadata.get("licensee_id")
            if licensee_id:
                session.run(
                    """
                    MERGE (l:Licensee {licensee_id: $licensee_id})
                    SET l.license_status = $license_status
                    WITH l
                    MATCH (a:Asset {asset_id: $asset_id})
                    MERGE (a)-[:LICENSED_TO]->(l)
                    """,
                    asset_id=asset_id,
                    licensee_id=str(licensee_id),
                    license_status=float(metadata.get("license_status", 0.0)),
                )

            for n in neighbors:
                n_id = str(n.get("asset_id", ""))
                if not n_id:
                    continue
                session.run(
                    """
                    MERGE (n:Asset {asset_id: $neighbor_asset_id})
                    SET n.modality = coalesce($modality, n.modality)
                    WITH n
                    MATCH (a:Asset {asset_id: $asset_id})
                    MERGE (a)-[r:SIMILAR_TO]->(n)
                    SET r.weight = $weight
                    """,
                    asset_id=asset_id,
                    neighbor_asset_id=n_id,
                    modality=n.get("modality"),
                    weight=float(n.get("similarity", 0.0)),
                )
                if bool(n.get("is_flagged", False)):
                    session.run(
                        """
                        MATCH (a:Asset {asset_id: $asset_id})
                        MATCH (n:Asset {asset_id: $neighbor_asset_id})
                        MERGE (a)-[f:FLAGGED_WITH]->(n)
                        SET f.weight = $weight
                        """,
                        asset_id=asset_id,
                        neighbor_asset_id=n_id,
                        weight=float(n.get("flagged_weight", 1.5)),
                    )

    def fetch_asset_neighborhood(self, asset_id: str, limit_assets: int = 64) -> dict[str, Any]:
        with self.driver.session(database=self.database) as session:
            records = session.run(
                """
                MATCH (q:Asset {asset_id: $asset_id})
                OPTIONAL MATCH (q)-[s:SIMILAR_TO]->(a1:Asset)
                OPTIONAL MATCH (a1)-[s2:SIMILAR_TO]->(a2:Asset)
                WITH q, collect(DISTINCT a1) + collect(DISTINCT a2) AS asset_nodes
                WITH q, [x IN asset_nodes WHERE x IS NOT NULL][..$limit_assets] AS assets

                UNWIND assets AS a
                OPTIONAL MATCH (a)-[:CREATED_BY]->(c:Creator)
                OPTIONAL MATCH (a)-[:LICENSED_TO]->(l:Licensee)
                OPTIONAL MATCH (q)-[sim:SIMILAR_TO]->(a)
                OPTIONAL MATCH (q)-[flg:FLAGGED_WITH]->(a)
                RETURN q.asset_id AS query_asset_id,
                       collect(DISTINCT {
                           asset_id: a.asset_id,
                           modality: a.modality,
                           source: a.source,
                           filename: a.filename,
                           is_flagged: coalesce(a.is_flagged, false),
                           creator_id: c.creator_id,
                           creator_trust_score: coalesce(c.trust_score, 0.5),
                           creator_tenure_months: coalesce(c.tenure_months, 12.0),
                           creator_verified: coalesce(c.verified, false),
                           licensee_id: l.licensee_id,
                           license_status: coalesce(l.license_status, 0.0),
                           similarity: coalesce(sim.weight, 0.0),
                           flagged_weight: coalesce(flg.weight, 0.0)
                       }) AS neighbors
                """,
                asset_id=asset_id,
                limit_assets=limit_assets,
            )
            row = records.single()

        if row is None:
            return {"query_asset_id": asset_id, "neighbors": []}

        return {
            "query_asset_id": row["query_asset_id"],
            "neighbors": [n for n in (row["neighbors"] or []) if n.get("asset_id")],
        }

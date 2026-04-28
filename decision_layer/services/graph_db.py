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
                    a.title = $title,
                    a.user_id = $user_id,
                    a.is_flagged = $is_flagged,
                    a.authorization_status = $authorization_status,
                    a.decision_label = $decision_label,
                    a.decision_confidence = $decision_confidence,
                    a.source_tier = $source_tier,
                    a.license_file_name = $license_file_name,
                    a.license_content_type = $license_content_type,
                    a.uploaded_at = $uploaded_at
                """,
                asset_id=asset_id,
                modality=metadata.get("modality"),
                source=metadata.get("source"),
                filename=metadata.get("filename"),
                title=metadata.get("title"),
                user_id=metadata.get("user_id"),
                is_flagged=bool(metadata.get("is_flagged", False)),
                authorization_status=metadata.get("authorization_status"),
                decision_label=metadata.get("decision_label"),
                decision_confidence=float(metadata.get("decision_confidence", 0.0)),
                source_tier=metadata.get("source_tier"),
                license_file_name=metadata.get("license_file_name"),
                license_content_type=metadata.get("license_content_type"),
                uploaded_at=metadata.get("uploaded_at"),
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

    def fetch_asset_relationship_graph(self, asset_id: str, limit_assets: int = 24) -> dict[str, Any]:
        with self.driver.session(database=self.database) as session:
            records = session.run(
                """
                MATCH (q:Asset {asset_id: $asset_id})
                OPTIONAL MATCH (q)-[r1:SIMILAR_TO|FLAGGED_WITH]->(neighbor:Asset)
                OPTIONAL MATCH (q)-[r2:CREATED_BY]->(creator:Creator)
                OPTIONAL MATCH (q)-[r3:LICENSED_TO]->(licensee:Licensee)
                WITH q,
                     collect(DISTINCT {
                         node: neighbor,
                         rel_type: type(r1),
                         rel_weight: coalesce(r1.weight, 0.0)
                     })[..$limit_assets] AS asset_links,
                     collect(DISTINCT {
                         node: creator,
                         rel_type: type(r2),
                         rel_weight: coalesce(r2.weight, 1.0)
                     }) AS creator_links,
                     collect(DISTINCT {
                         node: licensee,
                         rel_type: type(r3),
                         rel_weight: coalesce(r3.weight, 1.0)
                     }) AS licensee_links
                RETURN q.asset_id AS query_asset_id,
                       q {
                           .asset_id,
                           .modality,
                           .source,
                           .filename,
                           .title,
                           .user_id,
                           .authorization_status,
                           .decision_label,
                           .decision_confidence,
                           .is_flagged,
                           .source_tier,
                           .license_file_name,
                           .license_content_type,
                           .uploaded_at
                       } AS query_asset,
                       asset_links,
                       creator_links,
                       licensee_links
                """,
                asset_id=asset_id,
                limit_assets=limit_assets,
            )
            row = records.single()

        if row is None:
            return {"query_asset_id": asset_id, "nodes": [], "edges": []}

        query_asset = dict(row["query_asset"] or {})
        query_asset_id = str(query_asset.get("asset_id") or asset_id)

        nodes: list[dict[str, Any]] = [
            {
                "id": query_asset_id,
                "label": query_asset.get("filename") or query_asset_id,
                "type": "asset",
                "is_query": True,
                "metadata": query_asset,
            }
        ]
        edges: list[dict[str, Any]] = []
        seen_nodes = {query_asset_id}
        seen_edges: set[tuple[str, str, str]] = set()

        def add_link(raw_links: list[dict[str, Any]] | None, node_type: str) -> None:
            for raw in raw_links or []:
                node = raw.get("node")
                if node is None:
                    continue

                payload = dict(node)
                if node_type == "asset":
                    node_id = str(payload.get("asset_id", "")).strip()
                    label = payload.get("filename") or node_id
                elif node_type == "creator":
                    node_id = str(payload.get("creator_id", "")).strip()
                    label = node_id
                else:
                    node_id = str(payload.get("licensee_id", "")).strip()
                    label = node_id

                if not node_id:
                    continue

                if node_id not in seen_nodes:
                    nodes.append(
                        {
                            "id": node_id,
                            "label": label,
                            "type": node_type,
                            "is_query": False,
                            "metadata": payload,
                        }
                    )
                    seen_nodes.add(node_id)

                rel_type = str(raw.get("rel_type", "")).strip()
                edge_key = (query_asset_id, node_id, rel_type)
                if not rel_type or edge_key in seen_edges:
                    continue

                edges.append(
                    {
                        "source": query_asset_id,
                        "target": node_id,
                        "type": rel_type,
                        "weight": float(raw.get("rel_weight", 0.0)),
                    }
                )
                seen_edges.add(edge_key)

        add_link(row.get("asset_links"), "asset")
        add_link(row.get("creator_links"), "creator")
        add_link(row.get("licensee_links"), "licensee")

        return {
            "query_asset_id": query_asset_id,
            "nodes": nodes,
            "edges": edges,
        }

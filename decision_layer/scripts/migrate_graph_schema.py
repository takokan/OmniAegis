from __future__ import annotations

from decision_layer.services.graph_db import GraphDBService


def main() -> None:
    graph_db = GraphDBService.from_env()
    try:
        graph_db.run_migrations()
        print("Neo4j schema migration completed")
    finally:
        graph_db.close()


if __name__ == "__main__":
    main()

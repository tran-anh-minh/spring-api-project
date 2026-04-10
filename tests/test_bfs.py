"""Tests for BFS graph traversal over SQLite adjacency.

Tests cover: linear paths, cycles, edge type filtering, max depth,
bidirectional traversal, empty graphs, and multi-type filtering.
"""
import sqlite3
from datetime import datetime, timezone

import pytest

from db_wiki.core.store import init_schema


@pytest.fixture
def graph_db(initialized_db: sqlite3.Connection) -> sqlite3.Connection:
    """Seed an initialized DB with test entities and relationships for BFS.

    Graph topology:
        A --reads_from--> B --writes_to--> C --joins_with--> A  (cycle)
        A --fk_declared--> D
    Entity IDs: A=1, B=2, C=3, D=4
    """
    now = datetime.now(timezone.utc).isoformat()
    now_ts = int(datetime.now(timezone.utc).timestamp())

    # Insert 4 test tables as entities
    for name in ("A", "B", "C", "D"):
        initialized_db.execute(
            "INSERT INTO db_tables (table_name, schema_name, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (?, 'dbo', ?, ?, ?, ?)",
            (name, now, now_ts, now, now_ts),
        )

    # Insert relationships: A(1)->B(2) reads_from, B(2)->C(3) writes_to,
    # C(3)->A(1) joins_with (cycle), A(1)->D(4) fk_declared
    rels = [
        (1, 2, "reads_from"),
        (2, 3, "writes_to"),
        (3, 1, "joins_with"),
        (1, 4, "fk_declared"),
    ]
    for src, tgt, rtype in rels:
        initialized_db.execute(
            "INSERT INTO db_relationships (source_id, target_id, relationship_type, "
            "confidence, valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
            "VALUES (?, ?, ?, 1.0, ?, ?, ?, ?)",
            (src, tgt, rtype, now, now_ts, now, now_ts),
        )
    initialized_db.commit()
    return initialized_db


class TestBfsGraph:
    """Test suite for bfs_graph function."""

    def test_linear_traversal(self, graph_db: sqlite3.Connection) -> None:
        """Test 1: BFS from A traverses A->B->C and A->D."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(graph_db, start_id=1, max_depth=5)
        node_ids = [r["node_id"] for r in results]
        assert results[0]["node_id"] == 1
        assert results[0]["depth"] == 0
        # All nodes reachable bidirectionally
        assert set(node_ids) == {1, 2, 3, 4}

    def test_max_depth_limits_traversal(self, graph_db: sqlite3.Connection) -> None:
        """Test 2: max_depth=1 returns only start + direct neighbors."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(graph_db, start_id=1, max_depth=1)
        node_ids = [r["node_id"] for r in results]
        depths = {r["node_id"]: r["depth"] for r in results}
        # A at depth 0, direct neighbors at depth 1
        assert 1 in node_ids
        assert depths[1] == 0
        # Should NOT include nodes beyond depth 1
        for r in results:
            assert r["depth"] <= 1

    def test_edge_type_filter_single(self, graph_db: sqlite3.Connection) -> None:
        """Test 3: edge_types=['reads_from'] only follows reads_from edges."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(graph_db, start_id=1, max_depth=5, edge_types=["reads_from"])
        node_ids = [r["node_id"] for r in results]
        # From A, only reads_from edge goes to B. B has no reads_from outgoing.
        # Bidirectional: B->A via reads_from reverse. No further reads_from from B.
        assert 1 in node_ids
        assert 2 in node_ids
        # C should NOT be reachable via reads_from only
        assert 3 not in node_ids

    def test_cycle_detection(self, graph_db: sqlite3.Connection) -> None:
        """Test 4: Cycle A->B->C->A terminates without infinite loop."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(graph_db, start_id=1, max_depth=10)
        # Should return each node exactly once despite cycle
        node_ids = [r["node_id"] for r in results]
        assert len(node_ids) == len(set(node_ids)), "Cycle caused duplicate visits"

    def test_no_edges_returns_start(self, graph_db: sqlite3.Connection) -> None:
        """Test 5: BFS from isolated node returns just that node."""
        from db_wiki.graph.bfs import bfs_graph

        # Insert an isolated entity (id=5)
        now = datetime.now(timezone.utc).isoformat()
        now_ts = int(datetime.now(timezone.utc).timestamp())
        graph_db.execute(
            "INSERT INTO db_tables (table_name, schema_name, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES ('E', 'dbo', ?, ?, ?, ?)",
            (now, now_ts, now, now_ts),
        )
        graph_db.commit()

        results = bfs_graph(graph_db, start_id=5, max_depth=5)
        assert len(results) == 1
        assert results[0]["node_id"] == 5
        assert results[0]["depth"] == 0

    def test_bidirectional_traversal(self, graph_db: sqlite3.Connection) -> None:
        """Test 6: Bidirectional traversal - B is reachable from A AND A from B."""
        from db_wiki.graph.bfs import bfs_graph

        # From B, bidirectional should reach A (reverse of A->B reads_from)
        results = bfs_graph(graph_db, start_id=2, max_depth=1, bidirectional=True)
        node_ids = [r["node_id"] for r in results]
        assert 1 in node_ids, "A should be reachable from B bidirectionally"

    def test_path_tracking(self, graph_db: sqlite3.Connection) -> None:
        """Test 7: Each result includes path from start to that node."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(graph_db, start_id=1, max_depth=5)
        # Start node path is just [start_id]
        start_result = [r for r in results if r["node_id"] == 1][0]
        assert start_result["path"] == [1]
        # Each non-start result path should start with 1 and end with node_id
        for r in results:
            assert r["path"][0] == 1
            assert r["path"][-1] == r["node_id"]
            assert len(r["path"]) == r["depth"] + 1

    def test_multi_edge_type_filter(self, graph_db: sqlite3.Connection) -> None:
        """Test 8: edge_types=['reads_from', 'writes_to'] follows both types."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(
            graph_db, start_id=1, max_depth=5,
            edge_types=["reads_from", "writes_to"],
        )
        node_ids = [r["node_id"] for r in results]
        # A->B (reads_from), B->C (writes_to) should be reachable
        assert 2 in node_ids
        assert 3 in node_ids

    def test_edge_type_in_results(self, graph_db: sqlite3.Connection) -> None:
        """Test 9: Results include relationship_type as edge_type."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(graph_db, start_id=1, max_depth=1)
        # Start node has no edge_type (it's the origin)
        start = [r for r in results if r["node_id"] == 1][0]
        assert start["edge_type"] is None
        # Non-start nodes should have edge_type set
        non_start = [r for r in results if r["node_id"] != 1]
        for r in non_start:
            assert r["edge_type"] is not None
            assert isinstance(r["edge_type"], str)

    def test_default_edge_types_follows_all(self, graph_db: sqlite3.Connection) -> None:
        """Test 10: Default edge_types=None follows all relationship types."""
        from db_wiki.graph.bfs import bfs_graph

        results = bfs_graph(graph_db, start_id=1, max_depth=5)
        node_ids = [r["node_id"] for r in results]
        # All 4 nodes should be reachable with all edge types
        assert set(node_ids) == {1, 2, 3, 4}

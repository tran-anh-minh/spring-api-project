"""Tests for db_wiki/query/resolver.py and db_wiki/core/query_schema.py.

Tests follow TDD: RED first, then GREEN.
"""
import json
import sqlite3
from unittest.mock import patch

import pytest

from db_wiki.core.query_schema import get_query_schema_sql, init_query_schema
from db_wiki.core.schema import get_schema_sql
from db_wiki.query.resolver import (
    JoinStep,
    MetricDefinition,
    ResolvedEntity,
    define_metric,
    find_join_paths,
    get_all_metrics,
    get_metric,
    get_schema_version,
    resolve_concepts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory SQLite connection with full schema + query schema initialized."""
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    c.row_factory = sqlite3.Row
    c.executescript(get_schema_sql())
    init_query_schema(c)
    yield c
    c.close()


def _now_ts():
    import time
    return int(time.time())


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _insert_table(conn, name="Orders", description="Order table"):
    ts = _now_ts()
    iso = _now_iso()
    cur = conn.execute(
        "INSERT INTO db_tables (table_name, description, valid_from, valid_from_ts, "
        "recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?)",
        (name, description, iso, ts, iso, ts),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Schema DDL tests
# ---------------------------------------------------------------------------


def test_get_query_schema_sql_contains_wiki_pages():
    sql = get_query_schema_sql()
    assert "CREATE TABLE IF NOT EXISTS wiki_pages" in sql


def test_get_query_schema_sql_contains_derived_metrics():
    sql = get_query_schema_sql()
    assert "CREATE TABLE IF NOT EXISTS derived_metrics" in sql


def test_get_query_schema_sql_contains_query_cache():
    sql = get_query_schema_sql()
    assert "CREATE TABLE IF NOT EXISTS query_cache" in sql


def test_get_query_schema_sql_contains_current_wiki_pages_view():
    sql = get_query_schema_sql()
    assert "CREATE VIEW IF NOT EXISTS current_wiki_pages" in sql


def test_get_query_schema_sql_contains_current_derived_metrics_view():
    sql = get_query_schema_sql()
    assert "CREATE VIEW IF NOT EXISTS current_derived_metrics" in sql


def test_init_query_schema_creates_tables(conn):
    # Tables should exist after init
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "wiki_pages" in tables
    assert "derived_metrics" in tables
    assert "query_cache" in tables


def test_init_query_schema_creates_views(conn):
    views = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
    }
    assert "current_wiki_pages" in views
    assert "current_derived_metrics" in views


def test_init_query_schema_tables_empty(conn):
    assert conn.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM derived_metrics").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# resolve_concepts tests
# ---------------------------------------------------------------------------


def test_resolve_concepts_returns_resolved_entities(conn):
    from db_wiki.core.config import EmbeddingConfig

    cfg = EmbeddingConfig()
    mock_results = [("table", 1, 0.9), ("procedure", 2, 0.7)]

    with patch("db_wiki.query.resolver.hybrid_search", return_value=mock_results):
        # Insert matching entities in db
        ts = _now_ts()
        iso = _now_iso()
        conn.execute(
            "INSERT INTO db_tables (id, table_name, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (1, 'Orders', ?, ?, ?, ?)",
            (iso, ts, iso, ts),
        )
        conn.execute(
            "INSERT INTO db_procedures (id, procedure_name, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (2, 'usp_GetOrders', ?, ?, ?, ?)",
            (iso, ts, iso, ts),
        )
        conn.commit()

        results = resolve_concepts(conn, "customer orders", cfg)

    assert len(results) == 2
    assert all(isinstance(r, ResolvedEntity) for r in results)
    # Sorted by score descending
    assert results[0].score >= results[1].score
    assert results[0].entity_type == "table"
    assert results[0].entity_id == 1
    assert results[0].name == "Orders"
    assert results[1].entity_type == "procedure"
    assert results[1].entity_id == 2
    assert results[1].name == "usp_GetOrders"


def test_resolve_concepts_calls_hybrid_search(conn):
    from db_wiki.core.config import EmbeddingConfig

    cfg = EmbeddingConfig()
    with patch("db_wiki.query.resolver.hybrid_search", return_value=[]) as mock_hs:
        resolve_concepts(conn, "test query", cfg)
    mock_hs.assert_called_once_with(conn, "test query", cfg, limit=10)


def test_resolve_concepts_skips_missing_entities(conn):
    """hybrid_search may return IDs that don't exist — skip gracefully."""
    from db_wiki.core.config import EmbeddingConfig

    cfg = EmbeddingConfig()
    mock_results = [("table", 999, 0.8)]  # ID 999 doesn't exist

    with patch("db_wiki.query.resolver.hybrid_search", return_value=mock_results):
        results = resolve_concepts(conn, "test", cfg)

    assert results == []


# ---------------------------------------------------------------------------
# find_join_paths tests
# ---------------------------------------------------------------------------


def test_find_join_paths_calls_bfs_with_correct_edge_types(conn):
    with patch("db_wiki.query.resolver.bfs_graph", return_value=[]) as mock_bfs:
        find_join_paths(conn, 1, 2)
    mock_bfs.assert_called_once()
    call_kwargs = mock_bfs.call_args
    edge_types = call_kwargs.kwargs.get("edge_types") or call_kwargs.args[3]
    assert "fk_declared" in edge_types
    assert "fk_inferred" in edge_types
    assert "joins_with" in edge_types


def test_find_join_paths_returns_join_steps(conn):
    # BFS returns path: [1, 3, 2] meaning 1->3->2
    bfs_result = [
        {"node_id": 1, "depth": 0, "path": [1], "edge_type": None},
        {"node_id": 3, "depth": 1, "path": [1, 3], "edge_type": "fk_declared"},
        {"node_id": 2, "depth": 2, "path": [1, 3, 2], "edge_type": "fk_inferred"},
    ]

    ts = _now_ts()
    iso = _now_iso()
    for tid, name in [(1, "Orders"), (2, "Customers"), (3, "OrderDetails")]:
        conn.execute(
            "INSERT INTO db_tables (id, table_name, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?)",
            (tid, name, iso, ts, iso, ts),
        )
    conn.commit()

    with patch("db_wiki.query.resolver.bfs_graph", return_value=bfs_result):
        steps = find_join_paths(conn, 1, 2, max_depth=4)

    assert len(steps) > 0
    assert all(isinstance(s, JoinStep) for s in steps)


def test_find_join_paths_no_path_returns_empty(conn):
    bfs_result = [
        {"node_id": 1, "depth": 0, "path": [1], "edge_type": None},
    ]
    with patch("db_wiki.query.resolver.bfs_graph", return_value=bfs_result):
        steps = find_join_paths(conn, 1, 999)
    assert steps == []


# ---------------------------------------------------------------------------
# define_metric / get_metric / get_all_metrics tests
# ---------------------------------------------------------------------------


def test_define_metric_inserts_and_get_metric_returns(conn):
    row_id = define_metric(
        conn, "revenue", "SUM(order_total)", ["Orders"], "Total order revenue"
    )
    assert isinstance(row_id, int)
    assert row_id > 0

    m = get_metric(conn, "revenue")
    assert m is not None
    assert isinstance(m, MetricDefinition)
    assert m.name == "revenue"
    assert m.sql_fragment == "SUM(order_total)"
    assert m.source_tables == ["Orders"]
    assert m.description == "Total order revenue"


def test_get_metric_returns_none_for_missing(conn):
    result = get_metric(conn, "nonexistent_metric")
    assert result is None


def test_get_all_metrics_returns_all(conn):
    define_metric(conn, "revenue", "SUM(order_total)", ["Orders"])
    define_metric(conn, "avg_order", "AVG(order_total)", ["Orders"])
    metrics = get_all_metrics(conn)
    assert len(metrics) == 2
    names = {m.name for m in metrics}
    assert "revenue" in names
    assert "avg_order" in names


def test_define_metric_rejects_semicolons(conn):
    with pytest.raises(ValueError, match="(?i)semicolon|invalid|rejected"):
        define_metric(conn, "bad", "SUM(x); DROP TABLE foo", ["T"])


def test_define_metric_rejects_drop_keyword(conn):
    with pytest.raises(ValueError, match="(?i)drop|invalid|rejected|forbidden"):
        define_metric(conn, "bad", "DROP TABLE orders", ["Orders"])


def test_define_metric_rejects_insert_keyword(conn):
    with pytest.raises(ValueError, match="(?i)insert|invalid|rejected|forbidden"):
        define_metric(conn, "bad", "INSERT INTO foo VALUES (1)", ["foo"])


def test_define_metric_rejects_exec_keyword(conn):
    with pytest.raises(ValueError, match="(?i)exec|invalid|rejected|forbidden"):
        define_metric(conn, "bad", "EXEC sp_something", ["foo"])


def test_define_metric_rejects_delete_keyword(conn):
    with pytest.raises(ValueError, match="(?i)delete|invalid|rejected|forbidden"):
        define_metric(conn, "bad", "DELETE FROM orders", ["orders"])


def test_define_metric_rejects_update_keyword(conn):
    with pytest.raises(ValueError, match="(?i)update|invalid|rejected|forbidden"):
        define_metric(conn, "bad", "UPDATE orders SET x=1", ["orders"])


# ---------------------------------------------------------------------------
# get_schema_version tests
# ---------------------------------------------------------------------------


def test_get_schema_version_returns_zero_when_empty(conn):
    v = get_schema_version(conn)
    assert v == 0


def test_get_schema_version_returns_max_recorded_at_ts(conn):
    ts = _now_ts()
    iso = _now_iso()
    conn.execute(
        "INSERT INTO db_tables (table_name, valid_from, valid_from_ts, "
        "recorded_at, recorded_at_ts) VALUES ('T', ?, ?, ?, ?)",
        (iso, ts, iso, ts),
    )
    conn.commit()
    v = get_schema_version(conn)
    assert v == ts

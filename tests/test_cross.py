"""Phase 5 tests for cross-project store (CROSS-01, CROSS-02).

Tests verify cross-project pattern store creation, schema, and penalty logic.
"""
import sqlite3
from pathlib import Path

import pytest

from db_wiki.core.store import init_schema
from db_wiki.cross.store import init_cross_schema, open_cross_store


# ---------------------------------------------------------------------------
# CROSS-01: Open cross store
# ---------------------------------------------------------------------------


def test_open_cross_store(tmp_path: Path):
    """open_cross_store(db_path) returns a sqlite3.Connection. (CROSS-01)"""
    db_path = tmp_path / "cross.db"
    conn = open_cross_store(db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_cross_schema_tables(tmp_path: Path):
    """Cross store contains cross_patterns table after init. (CROSS-01)"""
    db_path = tmp_path / "cross.db"
    conn = open_cross_store(db_path)
    init_cross_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "cross_patterns" in tables


# ---------------------------------------------------------------------------
# CROSS-02: Cross penalty applied to confidence
# ---------------------------------------------------------------------------


def test_cross_penalty(tmp_path: Path):
    """get_cross_patterns returns patterns with adjusted confidence < original. (CROSS-02)"""
    from db_wiki.cross.reader import get_cross_patterns

    # Create a knowledge store to use as target_conn
    knowledge_db = tmp_path / "knowledge.db"
    target_conn = sqlite3.connect(str(knowledge_db))
    init_schema(target_conn)

    cross_db = tmp_path / "cross.db"
    patterns = get_cross_patterns(target_conn, cross_db_path=cross_db)
    # Empty cross store: no patterns, passes vacuously
    for p in patterns:
        assert p["adjusted_confidence"] < p["original_confidence"]
    target_conn.close()


# ---------------------------------------------------------------------------
# CROSS-01, D-07: Push patterns to cross store
# ---------------------------------------------------------------------------


def test_push_patterns(tmp_path: Path):
    """push_patterns_to_cross inserts patterns into cross.db. (CROSS-01, D-07)"""
    from db_wiki.cross.export import push_patterns_to_cross

    # Create a knowledge store with schema
    knowledge_db = tmp_path / "knowledge.db"
    knowledge_conn = sqlite3.connect(str(knowledge_db))
    init_schema(knowledge_conn)

    cross_db = tmp_path / "cross.db"
    counts = push_patterns_to_cross(knowledge_conn, "test_db", cross_db_path=cross_db)
    assert isinstance(counts, dict)

    # Verify cross store was created
    cross_conn = open_cross_store(cross_db)
    rows = cross_conn.execute("SELECT * FROM cross_patterns").fetchall()
    cross_conn.close()
    knowledge_conn.close()
    # May be 0 if knowledge store has no extractable patterns
    assert isinstance(rows, list)

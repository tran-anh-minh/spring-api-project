"""Phase 5 Wave 0 test stubs for cross-project store (CROSS-01, CROSS-02).

All tests are marked xfail — they verify the contracts that the Phase 5
cross-project implementation must satisfy.
"""
import sqlite3
from pathlib import Path

import pytest


XFAIL_REASON = "Phase 5 Wave 0 stub — not yet implemented"


# ---------------------------------------------------------------------------
# CROSS-01: Open cross store
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_open_cross_store(tmp_path: Path):
    """open_cross_store(tmp_path) returns a sqlite3.Connection. (CROSS-01)"""
    from db_wiki.cross.store import open_cross_store

    conn = open_cross_store(tmp_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_cross_schema_tables(tmp_path: Path):
    """Cross store contains cross_patterns table after open. (CROSS-01)"""
    from db_wiki.cross.store import open_cross_store

    conn = open_cross_store(tmp_path)
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


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_cross_penalty(tmp_path: Path):
    """get_cross_patterns returns patterns with adjusted confidence < original. (CROSS-02)"""
    from db_wiki.cross.reader import get_cross_patterns

    patterns = get_cross_patterns(tmp_path)
    # If any patterns exist their adjusted_confidence must be < original_confidence
    for p in patterns:
        assert p["adjusted_confidence"] < p["original_confidence"]


# ---------------------------------------------------------------------------
# CROSS-01, D-07: Push patterns to cross store
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_push_patterns(tmp_path: Path):
    """push_patterns_to_cross inserts patterns into cross.db. (CROSS-01, D-07)"""
    from db_wiki.cross.export import push_patterns_to_cross
    from db_wiki.cross.store import open_cross_store

    sample_patterns = [
        {"pattern_key": "orders_status_enum", "confidence": 0.9, "source_db": "db1"},
    ]
    push_patterns_to_cross(tmp_path, sample_patterns)

    conn = open_cross_store(tmp_path)
    rows = conn.execute("SELECT * FROM cross_patterns").fetchall()
    conn.close()
    assert len(rows) >= 1

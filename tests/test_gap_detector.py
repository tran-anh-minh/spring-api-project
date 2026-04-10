"""Tests for gap detection rules in db_wiki/learning/gap_detector.py.

Uses in-memory SQLite with Phase 1-2 + Phase 3 schema for isolation.
"""

import sqlite3
import time

import pytest

from db_wiki.core.schema import get_schema_sql
from db_wiki.learning.gap_detector import (
    detect_alias_clusters,
    detect_all_gaps,
    detect_coverage_gaps,
    detect_cross_sp_contradictions,
    detect_incomplete_state_machines,
    detect_low_confidence_facts,
    detect_missing_fks,
    detect_missing_joins,
    detect_orphan_tables,
    detect_pattern_anomalies,
    detect_stale_facts,
    detect_unresolved_calls,
    detect_unlabeled_enums,
    upsert_gaps,
)
from db_wiki.learning.models import GapInfo
from db_wiki.learning.schema_ext import init_learning_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """In-memory SQLite with full Phase 1-2 + Phase 3 schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(get_schema_sql())
    init_learning_schema(conn)
    yield conn
    conn.close()


NOW_TS = int(time.time())
NOW_ISO = "2026-04-11T00:00:00"


def _insert_table(conn: sqlite3.Connection, table_name: str, description: str | None = "desc") -> int:
    cur = conn.execute(
        "INSERT INTO db_tables (table_name, description, valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?)",
        (table_name, description, NOW_ISO, NOW_TS, NOW_ISO, NOW_TS),
    )
    conn.commit()
    return cur.lastrowid


def _insert_procedure(conn: sqlite3.Connection, proc_name: str, description: str | None = "desc") -> int:
    cur = conn.execute(
        "INSERT INTO db_procedures (procedure_name, description, valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?)",
        (proc_name, description, NOW_ISO, NOW_TS, NOW_ISO, NOW_TS),
    )
    conn.commit()
    return cur.lastrowid


def _insert_relationship(conn: sqlite3.Connection, source_id: int, target_id: int, rel_type: str, source_column: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO db_relationships (source_id, target_id, relationship_type, source_column, valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, target_id, rel_type, source_column, NOW_ISO, NOW_TS, NOW_ISO, NOW_TS),
    )
    conn.commit()
    return cur.lastrowid


def _insert_enum_value(conn: sqlite3.Connection, table_name: str, column_name: str, enum_value: str, enum_label: str | None, confidence: float = 0.9) -> int:
    cur = conn.execute(
        "INSERT INTO enum_values (table_name, column_name, enum_value, enum_label, confidence, detection_method, valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, 'case_when', ?, ?, ?, ?)",
        (table_name, column_name, enum_value, enum_label, confidence, NOW_ISO, NOW_TS, NOW_ISO, NOW_TS),
    )
    conn.commit()
    return cur.lastrowid


def _insert_column(conn: sqlite3.Connection, table_id: int, column_name: str, is_primary_key: int = 0) -> int:
    cur = conn.execute(
        "INSERT INTO db_columns (table_id, column_name, is_primary_key, valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (table_id, column_name, is_primary_key, NOW_ISO, NOW_TS, NOW_ISO, NOW_TS),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Test 1: detect_unlabeled_enums
# ---------------------------------------------------------------------------

def test_detect_unlabeled_enums_returns_gap_for_null_label(db):
    """detect_unlabeled_enums returns GapInfo for enum_values with NULL label."""
    _insert_enum_value(db, "orders", "status", "1", None)  # NULL label -> gap
    _insert_enum_value(db, "orders", "status", "2", "Active")  # labeled -> not a gap for this value

    gaps = detect_unlabeled_enums(db)

    assert len(gaps) == 1
    assert gaps[0].gap_type == "unlabeled_enum"
    assert gaps[0].entity_name == "orders.status"


def test_detect_unlabeled_enums_ignores_labeled(db):
    """detect_unlabeled_enums ignores columns where all values are labeled."""
    _insert_enum_value(db, "orders", "status", "1", "Active")
    _insert_enum_value(db, "orders", "status", "2", "Closed")

    gaps = detect_unlabeled_enums(db)

    assert len(gaps) == 0


def test_detect_unlabeled_enums_empty_label(db):
    """detect_unlabeled_enums treats empty string label same as NULL."""
    _insert_enum_value(db, "users", "type", "A", "")

    gaps = detect_unlabeled_enums(db)

    assert len(gaps) == 1
    assert gaps[0].entity_name == "users.type"


# ---------------------------------------------------------------------------
# Test 2: detect_orphan_tables
# ---------------------------------------------------------------------------

def test_detect_orphan_tables_returns_gap_for_table_with_no_relationships(db):
    """detect_orphan_tables returns GapInfo for tables with zero relationships."""
    tid = _insert_table(db, "orphan_table")

    gaps = detect_orphan_tables(db)

    names = [g.entity_name for g in gaps]
    assert "orphan_table" in names


def test_detect_orphan_tables_ignores_connected_table(db):
    """detect_orphan_tables ignores tables that appear in relationships."""
    tid1 = _insert_table(db, "orders")
    tid2 = _insert_table(db, "customers")
    _insert_relationship(db, tid1, tid2, "fk_declared")

    gaps = detect_orphan_tables(db)

    names = [g.entity_name for g in gaps]
    assert "orders" not in names
    assert "customers" not in names


# ---------------------------------------------------------------------------
# Test 3: detect_missing_joins
# ---------------------------------------------------------------------------

def test_detect_missing_joins_returns_gap_for_joins_with_no_fk(db):
    """detect_missing_joins returns GapInfo for joins_with without FK evidence."""
    tid1 = _insert_table(db, "orders")
    tid2 = _insert_table(db, "items")
    _insert_relationship(db, tid1, tid2, "joins_with")

    gaps = detect_missing_joins(db)

    assert len(gaps) >= 1
    assert any(g.gap_type == "missing_join_fk" for g in gaps)


def test_detect_missing_joins_ignores_joins_with_fk(db):
    """detect_missing_joins ignores joins_with when FK exists for same pair."""
    tid1 = _insert_table(db, "orders")
    tid2 = _insert_table(db, "items")
    _insert_relationship(db, tid1, tid2, "joins_with")
    _insert_relationship(db, tid1, tid2, "fk_declared")

    gaps = detect_missing_joins(db)

    assert len(gaps) == 0


# ---------------------------------------------------------------------------
# Test 4: detect_stale_facts
# ---------------------------------------------------------------------------

def test_detect_stale_facts_returns_gap_for_old_low_confidence(db):
    """detect_stale_facts returns GapInfo for old low-confidence enum values."""
    old_ts = int(time.time()) - 100 * 86400  # 100 days ago
    db.execute(
        "INSERT INTO enum_values (table_name, column_name, enum_value, confidence, detection_method, valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, 'case_when', ?, ?, ?, ?)",
        ("orders", "status", "1", 0.3, "2025-01-01T00:00:00", old_ts, "2025-01-01T00:00:00", old_ts),
    )
    db.commit()

    gaps = detect_stale_facts(db, staleness_days=90)

    assert len(gaps) >= 1
    assert any(g.gap_type == "stale_fact" for g in gaps)


def test_detect_stale_facts_ignores_recent_facts(db):
    """detect_stale_facts ignores recently recorded facts."""
    _insert_enum_value(db, "orders", "status", "1", None, confidence=0.3)  # recent

    gaps = detect_stale_facts(db, staleness_days=90)

    assert len(gaps) == 0


# ---------------------------------------------------------------------------
# Test 5: detect_coverage_gaps
# ---------------------------------------------------------------------------

def test_detect_coverage_gaps_returns_gap_for_table_without_description(db):
    """detect_coverage_gaps returns GapInfo for tables with NULL description."""
    _insert_table(db, "undocumented_table", description=None)

    gaps = detect_coverage_gaps(db)

    names = [g.entity_name for g in gaps]
    assert "undocumented_table" in names


def test_detect_coverage_gaps_returns_gap_for_sp_without_description(db):
    """detect_coverage_gaps returns GapInfo for SPs with NULL description."""
    _insert_procedure(db, "undocumented_sp", description=None)

    gaps = detect_coverage_gaps(db)

    names = [g.entity_name for g in gaps]
    assert "undocumented_sp" in names


def test_detect_coverage_gaps_ignores_documented_entities(db):
    """detect_coverage_gaps ignores tables/SPs with descriptions."""
    _insert_table(db, "documented_table", description="This is documented")
    _insert_procedure(db, "documented_sp", description="This is documented")

    gaps = detect_coverage_gaps(db)

    names = [g.entity_name for g in gaps]
    assert "documented_table" not in names
    assert "documented_sp" not in names


# ---------------------------------------------------------------------------
# Test 6: detect_all_gaps aggregates
# ---------------------------------------------------------------------------

def test_detect_all_gaps_returns_list(db):
    """detect_all_gaps returns a list even on empty database."""
    result = detect_all_gaps(db, NOW_TS, NOW_ISO)
    assert isinstance(result, list)


def test_detect_all_gaps_aggregates_multiple_rules(db):
    """detect_all_gaps returns results from multiple rules."""
    # Coverage gap (table without description)
    _insert_table(db, "no_desc_table", description=None)
    # Unlabeled enum
    _insert_enum_value(db, "orders", "status", "1", None)

    result = detect_all_gaps(db, NOW_TS, NOW_ISO)

    gap_types = {g.gap_type for g in result}
    assert "coverage_gap" in gap_types
    assert "unlabeled_enum" in gap_types


def test_detect_all_gaps_includes_orphan_table(db):
    """detect_all_gaps includes orphan tables."""
    _insert_table(db, "orphan")

    result = detect_all_gaps(db, NOW_TS, NOW_ISO)

    gap_types = {g.gap_type for g in result}
    assert "orphan_table" in gap_types


# ---------------------------------------------------------------------------
# Test 7: upsert_gaps skips open gaps
# ---------------------------------------------------------------------------

def test_upsert_gaps_skips_existing_open_gap(db):
    """upsert_gaps returns existing ID for gaps already with status='open'."""
    gap = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=0.7,
    )

    # First insert
    ids1 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    assert ids1[0] is not None
    first_id = ids1[0]

    # Second call -- should skip and return existing ID
    ids2 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    assert ids2[0] == first_id


def test_upsert_gaps_skips_investigating_gap(db):
    """upsert_gaps returns existing ID for gaps with status='investigating'."""
    gap = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=0.7,
    )
    ids1 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    first_id = ids1[0]

    # Update status to 'investigating'
    db.execute("UPDATE knowledge_gaps SET status='investigating' WHERE id=?", (first_id,))
    db.commit()

    ids2 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    assert ids2[0] == first_id


# ---------------------------------------------------------------------------
# Test 8: upsert_gaps skips permanent gaps
# ---------------------------------------------------------------------------

def test_upsert_gaps_skips_permanent_gap(db):
    """upsert_gaps returns None for gaps with status='permanent'."""
    gap = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=0.7,
    )
    ids1 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    first_id = ids1[0]

    # Mark as permanent
    db.execute("UPDATE knowledge_gaps SET status='permanent' WHERE id=?", (first_id,))
    db.commit()

    ids2 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    assert ids2[0] is None


# ---------------------------------------------------------------------------
# Test 9: upsert_gaps re-opens resolved gaps with expired cooldown
# ---------------------------------------------------------------------------

def test_upsert_gaps_reopens_resolved_gap_with_expired_cooldown(db):
    """upsert_gaps inserts new row for resolved gaps whose cooldown expired."""
    gap = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=0.7,
    )
    ids1 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    first_id = ids1[0]

    # Mark as resolved with cooldown_until_ts in the past
    expired_ts = NOW_TS - 3600  # 1 hour ago
    db.execute(
        "UPDATE knowledge_gaps SET status='resolved', cooldown_until_ts=? WHERE id=?",
        (expired_ts, first_id),
    )
    db.commit()

    # Should re-open (insert new row)
    ids2 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    assert ids2[0] is not None
    assert ids2[0] != first_id  # New row was created


def test_upsert_gaps_skips_resolved_gap_still_in_cooldown(db):
    """upsert_gaps returns None for resolved gaps still within cooldown."""
    gap = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=0.7,
    )
    ids1 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    first_id = ids1[0]

    # Mark as resolved with cooldown still active
    future_ts = NOW_TS + 3600  # 1 hour from now
    db.execute(
        "UPDATE knowledge_gaps SET status='resolved', cooldown_until_ts=? WHERE id=?",
        (future_ts, first_id),
    )
    db.commit()

    ids2 = upsert_gaps(db, [gap], NOW_TS, NOW_ISO)
    assert ids2[0] is None

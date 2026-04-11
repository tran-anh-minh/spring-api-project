"""Tests for L0/L1/L2 context assembler.

Tests for:
  - estimate_tokens: character-based token estimation
  - assemble_context: tiered context with budget enforcement
"""
import sqlite3

import pytest

from db_wiki.core.store import init_schema
from db_wiki.query.context import (
    DEFAULT_TOKEN_BUDGET,
    ContextResult,
    assemble_context,
    estimate_tokens,
)


# -- estimate_tokens ---------------------------------------------------------

def test_estimate_tokens_basic():
    text = "hello world"
    expected = max(1, int(len(text) / 3.5))
    assert estimate_tokens(text) == expected


def test_estimate_tokens_empty_returns_one():
    """Empty string returns 1 (minimum)."""
    assert estimate_tokens("") == 1


def test_estimate_tokens_longer_text():
    text = "a" * 350
    assert estimate_tokens(text) == 100


# -- Test DB helper ----------------------------------------------------------

def _now():
    from datetime import datetime, timezone
    ts = int(datetime.now(timezone.utc).timestamp())
    iso = datetime.now(timezone.utc).isoformat()
    return ts, iso


def _insert_table(conn, name: str, schema_name: str = "dbo") -> int:
    ts, iso = _now()
    cur = conn.execute(
        """INSERT INTO db_tables (table_name, schema_name, description,
           valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, schema_name, f"{name} table", iso, ts, iso, ts),
    )
    conn.commit()
    return cur.lastrowid


def _insert_column(conn, table_id: int, col_name: str, data_type: str = "INT",
                   is_pk: int = 0) -> int:
    ts, iso = _now()
    cur = conn.execute(
        """INSERT INTO db_columns (table_id, column_name, data_type, is_nullable,
           is_primary_key, valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)""",
        (table_id, col_name, data_type, is_pk, iso, ts, iso, ts),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db_with_tables():
    """In-memory DB with 5 core, 20 related, and 75+ other tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    # 5 core tables
    core_ids = []
    for i in range(5):
        tid = _insert_table(conn, f"CoreTable{i}")
        core_ids.append(tid)
        _insert_column(conn, tid, "id", "INT", is_pk=1)
        _insert_column(conn, tid, "name", "NVARCHAR(100)")

    # 20 related tables
    related_ids = []
    for i in range(20):
        tid = _insert_table(conn, f"RelatedTable{i}")
        related_ids.append(tid)
        _insert_column(conn, tid, "id", "INT", is_pk=1)
        _insert_column(conn, tid, "value", "DECIMAL(18,2)")

    # 75 background tables
    other_ids = []
    for i in range(75):
        tid = _insert_table(conn, f"OtherTable{i}")
        other_ids.append(tid)
        _insert_column(conn, tid, "id", "INT", is_pk=1)

    return conn, core_ids, related_ids, other_ids


# -- assemble_context tests --------------------------------------------------

def test_assemble_context_under_token_budget(db_with_tables):
    conn, core_ids, related_ids, _ = db_with_tables
    result = assemble_context(conn, core_ids, related_ids)
    assert isinstance(result, ContextResult)
    assert result.token_count <= DEFAULT_TOKEN_BUDGET


def test_assemble_context_l0_contains_all_table_names(db_with_tables):
    conn, core_ids, related_ids, _ = db_with_tables
    result = assemble_context(conn, core_ids, related_ids)
    # L0 section should contain all table names (at least as a summary list)
    assert "OtherTable0" in result.text or "OtherTable" in result.text


def test_assemble_context_l1_contains_related_table_columns(db_with_tables):
    conn, core_ids, related_ids, _ = db_with_tables
    result = assemble_context(conn, core_ids, related_ids)
    # L1 section should mention at least one related table
    assert "RelatedTable" in result.text


def test_assemble_context_l2_contains_core_table_detail(db_with_tables):
    conn, core_ids, related_ids, _ = db_with_tables
    result = assemble_context(conn, core_ids, related_ids)
    # L2 section should contain core table names and column details
    assert "CoreTable0" in result.text
    # L2 should include column details (data types)
    assert "INT" in result.text or "NVARCHAR" in result.text


def test_assemble_context_counts_are_accurate(db_with_tables):
    conn, core_ids, related_ids, _ = db_with_tables
    result = assemble_context(conn, core_ids, related_ids)
    assert result.l2_count == len(core_ids)
    assert result.l0_count >= 0
    assert result.l1_count >= 0


def test_assemble_context_token_count_matches_text(db_with_tables):
    conn, core_ids, related_ids, _ = db_with_tables
    result = assemble_context(conn, core_ids, related_ids)
    # Token count should be reasonable (within estimate)
    assert result.token_count == estimate_tokens(result.text)


def test_assemble_context_truncates_within_budget(db_with_tables):
    """Even with tiny budget, context stays within budget."""
    conn, core_ids, related_ids, _ = db_with_tables
    small_budget = 500
    result = assemble_context(conn, core_ids[:1], related_ids[:2], token_budget=small_budget)
    assert result.token_count <= small_budget


def test_assemble_context_empty_inputs(db_with_tables):
    """Empty entity lists return minimal L0 context."""
    conn, _, _, _ = db_with_tables
    result = assemble_context(conn, [], [])
    assert isinstance(result, ContextResult)
    assert result.l2_count == 0
    assert result.l1_count == 0

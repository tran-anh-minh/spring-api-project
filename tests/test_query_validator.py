"""Tests for SQL validator.

Tests for:
  - build_schema_map: builds dict[table_name, dict[col_name, data_type]] from DB
  - validate_sql: returns empty list for valid SQL
  - validate_sql: returns errors for unknown columns
  - validate_sql: returns errors for syntax errors
"""
import sqlite3

import pytest

from db_wiki.core.store import init_schema
from db_wiki.query.validator import build_schema_map, validate_sql


# -- Fixtures ----------------------------------------------------------------

def _now():
    from datetime import datetime, timezone
    ts = int(datetime.now(timezone.utc).timestamp())
    iso = datetime.now(timezone.utc).isoformat()
    return ts, iso


def _insert_table(conn, name: str) -> int:
    ts, iso = _now()
    cur = conn.execute(
        """INSERT INTO db_tables (table_name, schema_name, description,
           valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, 'dbo', ?, ?, ?, ?, ?)""",
        (name, f"{name} table", iso, ts, iso, ts),
    )
    conn.commit()
    return cur.lastrowid


def _insert_column(conn, table_id: int, col_name: str, data_type: str = "INT") -> int:
    ts, iso = _now()
    cur = conn.execute(
        """INSERT INTO db_columns (table_id, column_name, data_type, is_nullable,
           is_primary_key, valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, 1, 0, ?, ?, ?, ?)""",
        (table_id, col_name, data_type, iso, ts, iso, ts),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db_with_orders():
    """In-memory DB with an Orders table: OrderID INT, CustomerID INT, Status NVARCHAR."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "OrderID", "INT")
    _insert_column(conn, tid, "CustomerID", "INT")
    _insert_column(conn, tid, "Status", "NVARCHAR(50)")

    return conn


# -- build_schema_map --------------------------------------------------------

def test_build_schema_map_returns_correct_structure(db_with_orders):
    schema_map = build_schema_map(db_with_orders)
    assert isinstance(schema_map, dict)
    # Should have Orders table
    assert "Orders" in schema_map or "orders" in schema_map


def test_build_schema_map_contains_columns(db_with_orders):
    schema_map = build_schema_map(db_with_orders)
    # Normalize to case-insensitive lookup
    table_map = {k.lower(): v for k, v in schema_map.items()}
    assert "orders" in table_map
    cols = {c.lower() for c in table_map["orders"]}
    assert "orderid" in cols
    assert "customerid" in cols
    assert "status" in cols


def test_build_schema_map_empty_db():
    """Empty DB returns empty schema map."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    schema_map = build_schema_map(conn)
    assert isinstance(schema_map, dict)
    assert len(schema_map) == 0


# -- validate_sql: valid SQL -------------------------------------------------

def test_validate_sql_valid_select_returns_no_errors(db_with_orders):
    schema_map = build_schema_map(db_with_orders)
    errors = validate_sql("SELECT OrderID FROM Orders", schema_map)
    assert errors == []


def test_validate_sql_valid_select_star_returns_no_errors(db_with_orders):
    schema_map = build_schema_map(db_with_orders)
    errors = validate_sql("SELECT * FROM Orders", schema_map)
    assert errors == []


# -- validate_sql: unknown column/table errors -------------------------------

def test_validate_sql_unknown_column_returns_error(db_with_orders):
    schema_map = build_schema_map(db_with_orders)
    errors = validate_sql("SELECT nonexistent FROM Orders", schema_map)
    assert len(errors) > 0
    assert any("nonexistent" in e.lower() for e in errors)


def test_validate_sql_unknown_table_returns_error(db_with_orders):
    schema_map = build_schema_map(db_with_orders)
    errors = validate_sql("SELECT id FROM NonExistentTable", schema_map)
    assert len(errors) > 0


# -- validate_sql: syntax errors ---------------------------------------------

def test_validate_sql_syntax_error_returns_error():
    schema_map = {"Orders": {"OrderID": "INT"}}
    errors = validate_sql("INVALID SQL !!!", schema_map)
    assert len(errors) > 0
    # Error should mention syntax or parse issue
    combined = " ".join(errors).lower()
    assert "syntax" in combined or "error" in combined or "parse" in combined or "invalid" in combined


def test_validate_sql_empty_string_returns_error():
    schema_map = {}
    errors = validate_sql("", schema_map)
    # Empty SQL should fail parsing
    assert len(errors) > 0


# -- validate_sql: returns list type -----------------------------------------

def test_validate_sql_returns_list():
    schema_map = {"Orders": {"OrderID": "INT"}}
    errors = validate_sql("SELECT OrderID FROM Orders", schema_map)
    assert isinstance(errors, list)

"""Tests for db_wiki/query/wiki.py — on-demand wiki page generator.

Tests follow TDD: RED first, then GREEN.
"""
import sqlite3
import time
from datetime import datetime, timezone

import pytest

from db_wiki.core.query_schema import get_query_schema_sql, init_query_schema
from db_wiki.core.schema import get_schema_sql
from db_wiki.query.resolver import get_schema_version
from db_wiki.query.wiki import (
    generate_wiki_l0,
    generate_wiki_l1,
    generate_wiki_l2,
    generate_wiki_markdown,
    get_wiki_page,
    invalidate_wiki_cache,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    c.row_factory = sqlite3.Row
    c.executescript(get_schema_sql())
    init_query_schema(c)
    yield c
    c.close()


def _now_ts():
    return int(time.time())


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _insert_table(conn, name="Orders", description="Order table", table_id=None):
    ts = _now_ts()
    iso = _now_iso()
    if table_id:
        conn.execute(
            "INSERT INTO db_tables (id, table_name, description, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (table_id, name, description, iso, ts, iso, ts),
        )
    else:
        cur = conn.execute(
            "INSERT INTO db_tables (table_name, description, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, iso, ts, iso, ts),
        )
        table_id = cur.lastrowid
    conn.commit()
    return table_id


def _insert_column(conn, table_id, col_name, data_type="INT", is_pk=0, is_nullable=1):
    ts = _now_ts()
    iso = _now_iso()
    conn.execute(
        "INSERT INTO db_columns (table_id, column_name, data_type, is_nullable, is_primary_key, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (table_id, col_name, data_type, is_nullable, is_pk, iso, ts, iso, ts),
    )
    conn.commit()


def _insert_procedure(conn, name, description=None, proc_id=None):
    ts = _now_ts()
    iso = _now_iso()
    if proc_id:
        conn.execute(
            "INSERT INTO db_procedures (id, procedure_name, description, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (proc_id, name, description, iso, ts, iso, ts),
        )
    else:
        cur = conn.execute(
            "INSERT INTO db_procedures (procedure_name, description, valid_from, valid_from_ts, "
            "recorded_at, recorded_at_ts) VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, iso, ts, iso, ts),
        )
        proc_id = cur.lastrowid
    conn.commit()
    return proc_id


def _insert_relationship(conn, source_id, target_id, rel_type="fk_declared",
                         src_col=None, tgt_col=None):
    ts = _now_ts()
    iso = _now_iso()
    conn.execute(
        "INSERT INTO db_relationships (source_id, target_id, relationship_type, "
        "source_column, target_column, confidence, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?)",
        (source_id, target_id, rel_type, src_col, tgt_col, iso, ts, iso, ts),
    )
    conn.commit()


def _insert_sp_table_ref(conn, procedure_id, table_id):
    """Insert a reads_from relationship between procedure and table."""
    _insert_relationship(conn, procedure_id, table_id, "reads_from")


# ---------------------------------------------------------------------------
# generate_wiki_l0 tests
# ---------------------------------------------------------------------------


def test_generate_wiki_l0_table_summary(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "order_id", is_pk=1)
    _insert_column(conn, tid, "customer_id")
    _insert_column(conn, tid, "total", "DECIMAL")

    result = generate_wiki_l0(conn, "table", tid)
    assert "Orders" in result
    assert "3" in result or "columns" in result.lower()


def test_generate_wiki_l0_table_includes_relationship_count(conn):
    t1 = _insert_table(conn, "Orders")
    t2 = _insert_table(conn, "Customers")
    _insert_relationship(conn, t1, t2, "fk_declared")

    result = generate_wiki_l0(conn, "table", t1)
    assert "1" in result or "relationship" in result.lower()


def test_generate_wiki_l0_procedure_summary(conn):
    pid = _insert_procedure(conn, "usp_GetOrders", "Fetches all orders")
    tid = _insert_table(conn, "Orders")
    _insert_sp_table_ref(conn, pid, tid)

    result = generate_wiki_l0(conn, "procedure", pid)
    assert "usp_GetOrders" in result
    assert "1" in result or "table" in result.lower()


def test_generate_wiki_l0_unknown_entity_returns_not_found(conn):
    result = generate_wiki_l0(conn, "table", 99999)
    assert "not found" in result.lower() or result == ""


# ---------------------------------------------------------------------------
# generate_wiki_l1 tests
# ---------------------------------------------------------------------------


def test_generate_wiki_l1_table_includes_columns(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "order_id", "INT", is_pk=1)
    _insert_column(conn, tid, "customer_id", "INT")

    result = generate_wiki_l1(conn, "table", tid)
    assert "order_id" in result
    assert "customer_id" in result


def test_generate_wiki_l1_table_includes_l0_summary(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "id", "INT")

    result = generate_wiki_l1(conn, "table", tid)
    assert "Orders" in result


def test_generate_wiki_l1_procedure_includes_table_refs(conn):
    pid = _insert_procedure(conn, "usp_ProcessOrder")
    t1 = _insert_table(conn, "Orders")
    t2 = _insert_table(conn, "OrderItems")
    _insert_sp_table_ref(conn, pid, t1)
    _insert_sp_table_ref(conn, pid, t2)

    result = generate_wiki_l1(conn, "procedure", pid)
    assert "usp_ProcessOrder" in result
    # Should mention tables touched
    assert "Orders" in result or "OrderItems" in result


def test_generate_wiki_l1_procedure_includes_branch_count(conn):
    pid = _insert_procedure(conn, "usp_ProcessOrder")
    ts = _now_ts()
    iso = _now_iso()
    # Insert a branch
    conn.execute(
        "INSERT INTO sp_branches (procedure_id, branch_index, branch_type, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, 0, 'if', ?, ?, ?, ?)",
        (pid, iso, ts, iso, ts),
    )
    conn.commit()

    result = generate_wiki_l1(conn, "procedure", pid)
    assert "1" in result or "branch" in result.lower()


# ---------------------------------------------------------------------------
# generate_wiki_l2 tests
# ---------------------------------------------------------------------------


def test_generate_wiki_l2_table_includes_l1_content(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "order_id", "INT")

    result = generate_wiki_l2(conn, "table", tid)
    assert "Orders" in result
    assert "order_id" in result


def test_generate_wiki_l2_table_includes_enum_values(conn):
    tid = _insert_table(conn, "Orders")
    ts = _now_ts()
    iso = _now_iso()
    conn.execute(
        "INSERT INTO enum_values (table_name, column_name, enum_value, enum_label, "
        "confidence, detection_method, valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES ('Orders', 'status', '1', 'Active', 0.9, 'case_when', ?, ?, ?, ?)",
        (iso, ts, iso, ts),
    )
    conn.commit()

    result = generate_wiki_l2(conn, "table", tid)
    assert "Active" in result or "status" in result


def test_generate_wiki_l2_table_includes_state_transitions(conn):
    tid = _insert_table(conn, "Orders")
    ts = _now_ts()
    iso = _now_iso()
    conn.execute(
        "INSERT INTO state_transitions (table_name, column_name, from_value, to_value, "
        "confidence, valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES ('Orders', 'status', 'Pending', 'Active', 0.9, ?, ?, ?, ?)",
        (iso, ts, iso, ts),
    )
    conn.commit()

    result = generate_wiki_l2(conn, "table", tid)
    assert "Pending" in result or "Active" in result or "state" in result.lower()


def test_generate_wiki_l2_procedure_includes_branch_details(conn):
    pid = _insert_procedure(conn, "usp_ProcessOrder", "Process an order")
    ts = _now_ts()
    iso = _now_iso()
    conn.execute(
        "INSERT INTO sp_branches (procedure_id, branch_index, branch_type, condition_text, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, 0, 'if', 'status = 1', ?, ?, ?, ?)",
        (pid, iso, ts, iso, ts),
    )
    conn.commit()

    result = generate_wiki_l2(conn, "procedure", pid)
    assert "status = 1" in result or "branch" in result.lower() or "if" in result.lower()


# ---------------------------------------------------------------------------
# get_wiki_page cache tests
# ---------------------------------------------------------------------------


def test_get_wiki_page_generates_on_first_call(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "id", "INT")

    content = get_wiki_page(conn, "table", tid, "L0")
    assert content
    assert "Orders" in content


def test_get_wiki_page_caches_on_second_call(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "id", "INT")

    get_wiki_page(conn, "table", tid, "L0")
    get_wiki_page(conn, "table", tid, "L0")

    # Should only have 1 row in wiki_pages (not 2)
    count = conn.execute(
        "SELECT COUNT(*) FROM wiki_pages WHERE entity_type='table' AND entity_id=? AND tier='L0'",
        (tid,),
    ).fetchone()[0]
    assert count == 1


def test_get_wiki_page_invalidates_on_schema_version_change(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "id", "INT")

    # Get current schema_version to use for first cache entry
    schema_v1 = get_schema_version(conn)

    # Prime the cache with a known schema_version by inserting directly
    from db_wiki.query import wiki as wiki_mod
    wiki_mod._store_page(conn, "table", tid, "L0", "Orders - 1 columns, 0 relationships", schema_v1)

    # Bump schema_version by inserting a new table with a higher recorded_at_ts
    conn.execute(
        "INSERT INTO db_tables (table_name, valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES ('Customers', ?, ?, ?, ?)",
        (_now_iso(), schema_v1 + 1, _now_iso(), schema_v1 + 1),
    )
    conn.commit()

    # Second call should generate fresh content (new row)
    get_wiki_page(conn, "table", tid, "L0")

    # The old row should be invalidated; there should be exactly 1 current page
    current_count = conn.execute(
        "SELECT COUNT(*) FROM current_wiki_pages WHERE entity_type='table' AND entity_id=? AND tier='L0'",
        (tid,),
    ).fetchone()[0]
    assert current_count == 1

    # Total rows (including invalidated) should be 2
    total_count = conn.execute(
        "SELECT COUNT(*) FROM wiki_pages WHERE entity_type='table' AND entity_id=? AND tier='L0'",
        (tid,),
    ).fetchone()[0]
    assert total_count == 2


# ---------------------------------------------------------------------------
# invalidate_wiki_cache tests
# ---------------------------------------------------------------------------


def test_invalidate_wiki_cache_sets_invalidated_at(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "id", "INT")

    get_wiki_page(conn, "table", tid, "L0")
    count_before = conn.execute(
        "SELECT COUNT(*) FROM current_wiki_pages WHERE entity_type='table' AND entity_id=?",
        (tid,),
    ).fetchone()[0]
    assert count_before == 1

    invalidated = invalidate_wiki_cache(conn, "table", tid)
    assert invalidated == 1

    count_after = conn.execute(
        "SELECT COUNT(*) FROM current_wiki_pages WHERE entity_type='table' AND entity_id=?",
        (tid,),
    ).fetchone()[0]
    assert count_after == 0


def test_invalidate_wiki_cache_no_op_when_no_pages(conn):
    invalidated = invalidate_wiki_cache(conn, "table", 9999)
    assert invalidated == 0


# ---------------------------------------------------------------------------
# generate_wiki_markdown tests
# ---------------------------------------------------------------------------


def test_generate_wiki_markdown_produces_markdown_document(conn):
    tid = _insert_table(conn, "Orders", "Main orders table")
    _insert_column(conn, tid, "order_id", "INT", is_pk=1)
    _insert_column(conn, tid, "total", "DECIMAL")

    doc = generate_wiki_markdown(conn, "table", tid)
    # Should have a top-level header
    assert doc.startswith("#")
    assert "Orders" in doc
    # Should have multiple sections
    assert "##" in doc


def test_generate_wiki_markdown_includes_all_tiers(conn):
    tid = _insert_table(conn, "Orders")
    _insert_column(conn, tid, "order_id", "INT")

    doc = generate_wiki_markdown(conn, "table", tid)
    # L0 summary, L1 columns, L2 details
    lower_doc = doc.lower()
    assert "summary" in lower_doc or "orders" in lower_doc
    assert "detail" in lower_doc or "column" in lower_doc


def test_generate_wiki_markdown_procedure(conn):
    pid = _insert_procedure(conn, "usp_GetOrders", "Retrieves all orders")

    doc = generate_wiki_markdown(conn, "procedure", pid)
    assert "usp_GetOrders" in doc
    assert doc.startswith("#")

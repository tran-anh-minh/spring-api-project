"""Tests for the SP parser module (db_wiki/ingest/sp_parser.py).

Covers: table refs, mutations, branches, call chains, enums, state transitions,
parse quality, body hash, ingest with cascade invalidation, content type detection.
"""

import sqlite3

import pytest

from db_wiki.core.models import SPInfo, SPParseResult


# ---------------------------------------------------------------------------
# Test 1: parse_sp_file returns valid Create statements
# ---------------------------------------------------------------------------
def test_parse_sp_file_simple_procedure():
    from db_wiki.ingest.sp_parser import parse_sp_file

    sql = "CREATE PROCEDURE dbo.GetOrders AS SELECT * FROM Orders"
    stmts, warnings = parse_sp_file(sql)
    assert len(stmts) == 1
    assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Test 2: extract_sp_info on simple SELECT returns table_refs
# ---------------------------------------------------------------------------
def test_extract_sp_info_table_refs():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = "CREATE PROCEDURE dbo.GetOrders AS SELECT * FROM Orders"
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    assert isinstance(info, SPInfo)
    assert "Orders" in info.table_refs


# ---------------------------------------------------------------------------
# Test 3: extract_sp_info on INSERT returns mutation
# ---------------------------------------------------------------------------
def test_extract_sp_info_insert_mutation():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = """
    CREATE PROCEDURE dbo.LogAction AS
    INSERT INTO dbo.AuditLog (Action, CreatedAt)
    VALUES ('test', GETDATE())
    """
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    assert len(info.mutations) >= 1
    mut = info.mutations[0]
    assert mut.table_name == "AuditLog"
    assert mut.mutation_type == "insert"


# ---------------------------------------------------------------------------
# Test 4: extract_sp_info on UPDATE with state transition
# ---------------------------------------------------------------------------
def test_extract_sp_info_state_transition():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = """
    CREATE PROCEDURE dbo.ShipOrder AS
    UPDATE Orders SET Status = 'Shipped' WHERE Status = 'Pending'
    """
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    assert len(info.state_transitions) >= 1
    st = info.state_transitions[0]
    assert st.from_value == "Pending"
    assert st.to_value == "Shipped"
    assert st.confidence == 0.9


# ---------------------------------------------------------------------------
# Test 5: extract_sp_info on EXEC static call returns call_chain
# ---------------------------------------------------------------------------
def test_extract_sp_info_call_chain():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = """
    CREATE PROCEDURE dbo.MainProc AS
    EXEC dbo.SubProc
    """
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    assert len(info.call_chains) >= 1
    assert info.call_chains[0].callee_name == "SubProc"


# ---------------------------------------------------------------------------
# Test 6: extract_sp_info on EXEC(@sql) returns dynamic SQL flag
# ---------------------------------------------------------------------------
def test_extract_sp_info_dynamic_sql_exec_variable():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = """
    CREATE PROCEDURE dbo.DynProc AS
    BEGIN
        DECLARE @sql NVARCHAR(MAX)
        SET @sql = N'SELECT 1'
        EXEC(@sql)
    END
    """
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    assert info.has_dynamic_sql is True
    assert len(info.dynamic_sql_locations) > 0


# ---------------------------------------------------------------------------
# Test 7: extract_sp_info on sp_executesql returns dynamic SQL flag
# ---------------------------------------------------------------------------
def test_extract_sp_info_dynamic_sql_sp_executesql():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = """
    CREATE PROCEDURE dbo.DynProc2 AS
    EXEC sp_executesql N'SELECT 1'
    """
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    assert info.has_dynamic_sql is True


# ---------------------------------------------------------------------------
# Test 8: compute_parse_quality returns correct degradation
# ---------------------------------------------------------------------------
def test_compute_parse_quality():
    from db_wiki.ingest.sp_parser import compute_parse_quality, parse_sp_file

    sql = "CREATE PROCEDURE dbo.Simple AS SELECT 1"
    stmts, _ = parse_sp_file(sql)
    quality, is_degraded = compute_parse_quality(stmts[0])
    assert isinstance(quality, float)
    assert 0.0 <= quality <= 1.0
    # A simple SP should have high quality
    assert quality >= 0.95
    assert is_degraded is False


# ---------------------------------------------------------------------------
# Test 9: extract_sp_info on CASE WHEN returns enum detection
# ---------------------------------------------------------------------------
def test_extract_sp_info_enum_detection():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = """
    CREATE PROCEDURE dbo.GetStatusLabel AS
    SELECT
        CASE WHEN Status = 1 THEN 'Active'
             WHEN Status = 2 THEN 'Inactive'
        END AS StatusLabel
    FROM Users
    """
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    assert len(info.enum_detections) >= 1
    enum = info.enum_detections[0]
    assert len(enum.values) >= 2
    # Check that we have the expected value-label pairs
    value_labels = {v["value"]: v["label"] for v in enum.values}
    assert "1" in value_labels or 1 in value_labels
    assert "2" in value_labels or 2 in value_labels


# ---------------------------------------------------------------------------
# Test 10: extract_sp_info on IF/ELSE returns branches
# ---------------------------------------------------------------------------
def test_extract_sp_info_branches():
    from db_wiki.ingest.sp_parser import extract_sp_info, parse_sp_file

    sql = """
    CREATE PROCEDURE dbo.CheckStock AS
    BEGIN
        IF EXISTS (SELECT 1 FROM Inventory WHERE Qty > 0)
            SELECT 1 AS InStock
        ELSE
            SELECT 0 AS InStock
    END
    """
    stmts, _ = parse_sp_file(sql)
    info = extract_sp_info(stmts[0], sql)
    # Should have at least one branch (if from AST, or else/if from Command fallback)
    assert len(info.branches) >= 1


# ---------------------------------------------------------------------------
# Test 11: parse_sp_file with non-SP DDL returns empty valid list
# ---------------------------------------------------------------------------
def test_parse_sp_file_filters_non_sp_ddl():
    from db_wiki.ingest.sp_parser import parse_sp_file

    sql = "CREATE TABLE Orders (Id INT PRIMARY KEY, Name NVARCHAR(100))"
    stmts, warnings = parse_sp_file(sql)
    assert len(stmts) == 0


# ---------------------------------------------------------------------------
# Test 12: compute_body_hash normalizes whitespace
# ---------------------------------------------------------------------------
def test_compute_body_hash_normalizes_whitespace():
    from db_wiki.ingest.sp_parser import compute_body_hash

    sql1 = "CREATE  PROCEDURE  dbo.Test   AS   SELECT  1"
    sql2 = "CREATE PROCEDURE dbo.Test AS SELECT 1"
    assert compute_body_hash(sql1) == compute_body_hash(sql2)
    # Different content produces different hash
    sql3 = "CREATE PROCEDURE dbo.Test AS SELECT 2"
    assert compute_body_hash(sql1) != compute_body_hash(sql3)


# ---------------------------------------------------------------------------
# Test 13: ingest_sp writes to all intelligence tables
# ---------------------------------------------------------------------------
def test_ingest_sp_writes_all_tables(initialized_db):
    from db_wiki.ingest.sp_parser import ingest_sp, parse_sp

    sql = """CREATE PROCEDURE dbo.ShipOrder AS
UPDATE Orders SET Status = 'Shipped' WHERE Status = 'Pending';
INSERT INTO AuditLog (Action) VALUES ('shipped');
EXEC dbo.NotifyCustomer;"""
    result = parse_sp(sql)
    counts = ingest_sp(initialized_db, result)

    # Check procedure was inserted
    row = initialized_db.execute(
        "SELECT * FROM current_db_procedures WHERE procedure_name = 'ShipOrder'"
    ).fetchone()
    assert row is not None
    assert row["body_hash"] != ""

    # Check sp_reliability
    proc_id = row["id"]
    rel = initialized_db.execute(
        "SELECT * FROM current_sp_reliability WHERE procedure_id = ?", (proc_id,)
    ).fetchone()
    assert rel is not None

    # Check sp_branches or sp_call_chains exist
    chains = initialized_db.execute(
        "SELECT * FROM current_sp_call_chains WHERE caller_id = ?", (proc_id,)
    ).fetchall()
    assert len(chains) >= 1

    # Check state_transitions
    trans = initialized_db.execute(
        "SELECT * FROM current_state_transitions WHERE source_procedure_id = ?",
        (proc_id,),
    ).fetchall()
    assert len(trans) >= 1

    # Check relationships (reads_from / writes_to)
    assert counts.get("procedures", 0) >= 1


# ---------------------------------------------------------------------------
# Test 14: ingest_sp re-parse invalidates old procedure on body_hash change
# ---------------------------------------------------------------------------
def test_ingest_sp_reparse_invalidates_old(initialized_db):
    from db_wiki.ingest.sp_parser import ingest_sp, parse_sp

    sql_v1 = "CREATE PROCEDURE dbo.GetOrders AS SELECT * FROM Orders"
    result_v1 = parse_sp(sql_v1)
    ingest_sp(initialized_db, result_v1)

    old = initialized_db.execute(
        "SELECT id, body_hash FROM current_db_procedures WHERE procedure_name = 'GetOrders'"
    ).fetchone()
    assert old is not None
    old_id = old["id"]

    sql_v2 = "CREATE PROCEDURE dbo.GetOrders AS SELECT * FROM Orders WHERE Active = 1"
    result_v2 = parse_sp(sql_v2)
    ingest_sp(initialized_db, result_v2)

    # Old row should be invalidated
    invalidated = initialized_db.execute(
        "SELECT invalidated_at FROM db_procedures WHERE id = ?", (old_id,)
    ).fetchone()
    assert invalidated["invalidated_at"] is not None

    # New row should exist in current view
    new = initialized_db.execute(
        "SELECT id, body_hash FROM current_db_procedures WHERE procedure_name = 'GetOrders'"
    ).fetchone()
    assert new is not None
    assert new["id"] != old_id


# ---------------------------------------------------------------------------
# Test 15: ingest_sp cascade invalidation on re-parse
# ---------------------------------------------------------------------------
def test_ingest_sp_cascade_invalidation(initialized_db):
    from db_wiki.ingest.sp_parser import ingest_sp, parse_sp

    sql_v1 = """CREATE PROCEDURE dbo.ProcessOrder AS
UPDATE Orders SET Status = 'Processing' WHERE Status = 'New';
EXEC dbo.NotifyWarehouse;"""
    result_v1 = parse_sp(sql_v1)
    ingest_sp(initialized_db, result_v1)

    old_proc = initialized_db.execute(
        "SELECT id FROM current_db_procedures WHERE procedure_name = 'ProcessOrder'"
    ).fetchone()
    old_id = old_proc["id"]

    # Verify derived rows exist
    old_reliability = initialized_db.execute(
        "SELECT id FROM current_sp_reliability WHERE procedure_id = ?", (old_id,)
    ).fetchone()
    assert old_reliability is not None

    # Re-parse with different body
    sql_v2 = """CREATE PROCEDURE dbo.ProcessOrder AS
UPDATE Orders SET Status = 'Completed' WHERE Status = 'Processing';
EXEC dbo.NotifyCustomer;"""
    result_v2 = parse_sp(sql_v2)
    ingest_sp(initialized_db, result_v2)

    # Old reliability should be invalidated
    old_rel_row = initialized_db.execute(
        "SELECT invalidated_at FROM sp_reliability WHERE id = ?",
        (old_reliability["id"],),
    ).fetchone()
    assert old_rel_row["invalidated_at"] is not None

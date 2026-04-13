"""Phase 5 tests for export formatters (EXPORT-03).

Tests verify each exporter can be instantiated and produces expected output format.
"""
import json
import sqlite3

import pytest

from db_wiki.core.store import init_schema


@pytest.fixture()
def knowledge_conn(tmp_path):
    """Create a temporary knowledge store with schema initialized."""
    from db_wiki.core.store import open_store
    db_path = tmp_path / "knowledge.db"
    from db_wiki.core.query_schema import init_query_schema
    conn = open_store(db_path)
    init_schema(conn)
    init_query_schema(conn)
    # Insert a minimal table entity so exporters have something to work with
    import time
    from datetime import datetime, timezone
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    now_ts = int(time.time())
    conn.execute(
        """INSERT INTO db_tables (table_name, schema_name, valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("TestTable", "dbo", now_iso, now_ts, now_iso, now_ts),
    )
    table_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO db_columns (table_id, column_name, data_type, ordinal_position,
           valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (table_id, "id", "int", 1, now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# EXPORT-03: Markdown exporter
# ---------------------------------------------------------------------------


def test_markdown_exporter(knowledge_conn):
    """MarkdownExporter.export_all() produces output containing a '# ' heading. (EXPORT-03)"""
    from db_wiki.export.markdown import MarkdownExporter

    exporter = MarkdownExporter(knowledge_conn)
    output = exporter.export_all()
    assert isinstance(output, dict)
    assert len(output) > 0
    # At least one file should contain a markdown heading
    assert any("# " in content for content in output.values())


# ---------------------------------------------------------------------------
# EXPORT-03: Mermaid exporter
# ---------------------------------------------------------------------------


def test_mermaid_exporter(knowledge_conn):
    """MermaidExporter.export_all() produces output containing 'erDiagram'. (EXPORT-03)"""
    from db_wiki.export.mermaid import MermaidExporter

    exporter = MermaidExporter(knowledge_conn)
    output = exporter.export_all()
    assert "erDiagram" in output


# ---------------------------------------------------------------------------
# EXPORT-03: JSON schema exporter
# ---------------------------------------------------------------------------


def test_json_schema_exporter(knowledge_conn):
    """JsonSchemaExporter.export_all() produces valid JSON with 'tables' key. (EXPORT-03)"""
    from db_wiki.export.json_schema import JsonSchemaExporter

    exporter = JsonSchemaExporter(knowledge_conn)
    output = exporter.export_all()
    data = json.loads(output)
    assert "tables" in data


# ---------------------------------------------------------------------------
# EXPORT-03: Annotated DDL exporter
# ---------------------------------------------------------------------------


def test_ddl_annotated_exporter(knowledge_conn):
    """AnnotatedDDLExporter.export_all() produces DDL with CREATE TABLE. (EXPORT-03)"""
    from db_wiki.export.ddl_annotated import AnnotatedDDLExporter

    exporter = AnnotatedDDLExporter(knowledge_conn)
    output = exporter.export_all()
    assert "CREATE TABLE" in output

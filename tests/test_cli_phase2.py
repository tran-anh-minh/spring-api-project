"""Tests for Phase 2 CLI commands: search, lineage, sp-info (02-05).

Uses typer.testing.CliRunner. Tests verify command output and argument handling.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from db_wiki.cli.app import app

runner = CliRunner()


@pytest.fixture
def store_with_data(tmp_path: Path) -> Path:
    """Create a knowledge store with sample data for CLI commands."""
    store = tmp_path / ".db-wiki"

    # Init store
    result = runner.invoke(app, ["init", "--store-path", str(store)])
    assert result.exit_code == 0, result.output

    # Insert sample data
    db_path = store / "knowledge.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")

    from db_wiki.core.store import init_schema

    init_schema(conn)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_ts = int(now.timestamp())

    # Tables
    conn.execute(
        "INSERT INTO db_tables (table_name, schema_name, description, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Orders", "dbo", "Order table", now_iso, now_ts, now_iso, now_ts),
    )
    orders_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO db_tables (table_name, schema_name, description, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Customers", "dbo", "Customer table", now_iso, now_ts, now_iso, now_ts),
    )
    customers_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # A procedure
    conn.execute(
        "INSERT INTO db_procedures (procedure_name, schema_name, description, body_hash, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("GetOrders", "dbo", "Gets orders", "abc123", now_iso, now_ts, now_iso, now_ts),
    )
    proc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # A relationship (for lineage)
    conn.execute(
        "INSERT INTO db_relationships (source_id, target_id, relationship_type, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (proc_id, orders_id, "reads_from", now_iso, now_ts, now_iso, now_ts),
    )

    # FTS entities for search
    conn.execute(
        "INSERT OR REPLACE INTO fts_entities (entity_type, entity_name, description, entity_id) "
        "VALUES (?, ?, ?, ?)",
        ("table", "Orders", "Order table", orders_id),
    )
    conn.execute(
        "INSERT OR REPLACE INTO fts_entities (entity_type, entity_name, description, entity_id) "
        "VALUES (?, ?, ?, ?)",
        ("table", "Customers", "Customer table", customers_id),
    )

    conn.commit()
    conn.close()
    return store


# ---- search command tests ----

class TestSearchCommand:
    def test_search_returns_results(self, store_with_data: Path):
        result = runner.invoke(
            app, ["search", "orders", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 0, result.output
        assert "Orders" in result.output

    def test_search_fts_weight_option(self, store_with_data: Path):
        result = runner.invoke(
            app,
            ["search", "orders", "--store-path", str(store_with_data), "--fts-weight", "1.0"],
        )
        assert result.exit_code == 0, result.output

    def test_search_no_store(self, tmp_path: Path):
        store = tmp_path / "nonexistent"
        result = runner.invoke(app, ["search", "test", "--store-path", str(store)])
        assert result.exit_code == 1

    def test_search_accepts_limit(self, store_with_data: Path):
        result = runner.invoke(
            app,
            ["search", "table", "--store-path", str(store_with_data), "--limit", "1"],
        )
        assert result.exit_code == 0, result.output

    def test_search_accepts_store_path(self, store_with_data: Path):
        """search command accepts --store-path option."""
        result = runner.invoke(
            app, ["search", "orders", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 0


# ---- lineage command tests ----

class TestLineageCommand:
    def test_lineage_returns_results(self, store_with_data: Path):
        result = runner.invoke(
            app, ["lineage", "Orders", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 0, result.output

    def test_lineage_with_depth_and_edge_types(self, store_with_data: Path):
        result = runner.invoke(
            app,
            [
                "lineage",
                "Orders",
                "--store-path",
                str(store_with_data),
                "--max-depth",
                "1",
                "--edge-types",
                "reads_from,writes_to",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_lineage_entity_not_found(self, store_with_data: Path):
        result = runner.invoke(
            app, ["lineage", "NonExistent", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 1

    def test_lineage_no_store(self, tmp_path: Path):
        store = tmp_path / "nonexistent"
        result = runner.invoke(app, ["lineage", "Orders", "--store-path", str(store)])
        assert result.exit_code == 1

    def test_lineage_accepts_store_path(self, store_with_data: Path):
        """lineage command accepts --store-path option."""
        result = runner.invoke(
            app, ["lineage", "Orders", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 0


# ---- sp-info command tests ----

class TestSpInfoCommand:
    def test_sp_info_returns_details(self, store_with_data: Path):
        result = runner.invoke(
            app, ["sp-info", "GetOrders", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 0, result.output
        assert "GetOrders" in result.output
        assert "dbo" in result.output

    def test_sp_info_not_found(self, store_with_data: Path):
        result = runner.invoke(
            app, ["sp-info", "NonExistent", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 1

    def test_sp_info_no_store(self, tmp_path: Path):
        store = tmp_path / "nonexistent"
        result = runner.invoke(app, ["sp-info", "GetOrders", "--store-path", str(store)])
        assert result.exit_code == 1

    def test_sp_info_accepts_store_path(self, store_with_data: Path):
        """sp-info command accepts --store-path option."""
        result = runner.invoke(
            app, ["sp-info", "GetOrders", "--store-path", str(store_with_data)]
        )
        assert result.exit_code == 0


# ---- help text tests ----

class TestHelpIncludes:
    def test_help_lists_search(self):
        result = runner.invoke(app, ["--help"])
        assert "search" in result.output

    def test_help_lists_lineage(self):
        result = runner.invoke(app, ["--help"])
        assert "lineage" in result.output

    def test_help_lists_sp_info(self):
        result = runner.invoke(app, ["--help"])
        assert "sp-info" in result.output

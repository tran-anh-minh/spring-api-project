"""Tests for the extended CLI ingest command (directory, glob, --type flag)."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner
import yaml

from db_wiki.cli.app import app
from db_wiki.core.config import write_default_config
from db_wiki.core.store import init_schema, open_store

runner = CliRunner()


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    """Create a fully initialized knowledge store in a temp directory."""
    store = tmp_path / ".db-wiki"
    store.mkdir()
    write_default_config(store)
    db_path = store / "knowledge.db"
    conn = open_store(db_path)
    init_schema(conn)
    conn.close()
    return store


@pytest.fixture
def sql_dir(tmp_path: Path) -> Path:
    """Create a directory with sample SQL files."""
    d = tmp_path / "sql_files"
    d.mkdir()

    (d / "schema.sql").write_text(
        "CREATE TABLE Orders (Id INT PRIMARY KEY, Name NVARCHAR(100))",
        encoding="utf-8",
    )
    (d / "GetOrders.sql").write_text(
        "CREATE PROCEDURE dbo.GetOrders AS SELECT * FROM Orders",
        encoding="utf-8",
    )
    (d / "UpdateStatus.sql").write_text(
        "CREATE PROCEDURE dbo.UpdateStatus AS UPDATE Orders SET Status = 'Active' WHERE Status = 'Inactive'",
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# Test 1: ingest with a directory path ingests all .sql files
# ---------------------------------------------------------------------------
def test_ingest_directory(store_dir: Path, sql_dir: Path):
    result = runner.invoke(
        app,
        ["ingest", str(sql_dir), "--store-path", str(store_dir)],
    )
    assert result.exit_code == 0
    assert "3" in result.output or "files" in result.output.lower()


# ---------------------------------------------------------------------------
# Test 2: ingest with a glob pattern
# ---------------------------------------------------------------------------
def test_ingest_glob_pattern(store_dir: Path, sql_dir: Path, monkeypatch):
    # Use a glob pattern pointing to the sql_dir
    monkeypatch.chdir(sql_dir)
    result = runner.invoke(
        app,
        ["ingest", "*.sql", "--store-path", str(store_dir)],
    )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Test 3: ingest --type sp forces SP parsing
# ---------------------------------------------------------------------------
def test_ingest_force_sp_type(store_dir: Path, sql_dir: Path):
    sp_file = sql_dir / "GetOrders.sql"
    result = runner.invoke(
        app,
        ["ingest", str(sp_file), "--store-path", str(store_dir), "--type", "sp"],
    )
    assert result.exit_code == 0
    assert "procedure" in result.output.lower() or "sp" in result.output.lower()


# ---------------------------------------------------------------------------
# Test 4: ingest --type ddl forces DDL parsing
# ---------------------------------------------------------------------------
def test_ingest_force_ddl_type(store_dir: Path, sql_dir: Path):
    ddl_file = sql_dir / "schema.sql"
    result = runner.invoke(
        app,
        ["ingest", str(ddl_file), "--store-path", str(store_dir), "--type", "ddl"],
    )
    assert result.exit_code == 0
    assert "table" in result.output.lower()


# ---------------------------------------------------------------------------
# Test 5: ingest without --type auto-detects content type
# ---------------------------------------------------------------------------
def test_ingest_auto_detect(store_dir: Path, sql_dir: Path):
    sp_file = sql_dir / "GetOrders.sql"
    result = runner.invoke(
        app,
        ["ingest", str(sp_file), "--store-path", str(store_dir)],
    )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Test 6: ingest with directory reports summary
# ---------------------------------------------------------------------------
def test_ingest_directory_summary(store_dir: Path, sql_dir: Path):
    result = runner.invoke(
        app,
        ["ingest", str(sql_dir), "--store-path", str(store_dir)],
    )
    assert result.exit_code == 0
    # Should contain total or summary info
    output_lower = result.output.lower()
    assert "total" in output_lower or "file" in output_lower


# ---------------------------------------------------------------------------
# Test 7: ingest skips files that exceed max_file_size_mb
# ---------------------------------------------------------------------------
def test_ingest_skips_large_files(store_dir: Path, tmp_path: Path):
    # Modify config to set a very small max file size
    config_path = store_dir / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["ingest"]["max_file_size_mb"] = 0  # 0 MB = reject everything
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)

    sql_file = tmp_path / "big.sql"
    sql_file.write_text("CREATE TABLE T (Id INT)", encoding="utf-8")

    result = runner.invoke(
        app,
        ["ingest", str(sql_file), "--store-path", str(store_dir)],
    )
    # Should skip or warn about the file
    assert "skip" in result.output.lower() or "large" in result.output.lower() or result.exit_code != 0


# ---------------------------------------------------------------------------
# Test 8: ingest --type defaults to None (auto-detect)
# ---------------------------------------------------------------------------
def test_ingest_type_defaults_none(store_dir: Path, sql_dir: Path):
    ddl_file = sql_dir / "schema.sql"
    result = runner.invoke(
        app,
        ["ingest", str(ddl_file), "--store-path", str(store_dir)],
    )
    assert result.exit_code == 0
    # Auto-detect should parse DDL as DDL
    assert "table" in result.output.lower()

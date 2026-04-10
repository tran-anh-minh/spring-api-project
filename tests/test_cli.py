"""Tests for the Typer CLI with init, connect, and ingest commands.

Uses typer.testing.CliRunner for all tests — no subprocess calls needed.
"""
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from db_wiki.cli.app import app

runner = CliRunner()


def test_help():
    """--help exits 0 and lists init, connect, ingest commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "connect" in result.output
    assert "ingest" in result.output


def test_init(tmp_path: Path):
    """init creates .db-wiki/ with config.yaml and knowledge.db."""
    store = tmp_path / ".db-wiki"
    result = runner.invoke(app, ["init", "--store-path", str(store)])
    assert result.exit_code == 0, result.output
    assert (store / "config.yaml").exists()
    assert (store / "knowledge.db").exists()


def test_init_creates_schema(tmp_path: Path):
    """init creates knowledge.db with the schema tables."""
    store = tmp_path / ".db-wiki"
    runner.invoke(app, ["init", "--store-path", str(store)])

    conn = sqlite3.connect(str(store / "knowledge.db"))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "db_tables" in tables


def test_init_custom_path(tmp_path: Path):
    """init --store-path custom creates at the custom location."""
    custom = tmp_path / "custom"
    result = runner.invoke(app, ["init", "--store-path", str(custom)])
    assert result.exit_code == 0, result.output
    assert (custom / "config.yaml").exists()
    assert (custom / "knowledge.db").exists()


def test_init_idempotent(tmp_path: Path):
    """Calling init twice on the same store prints 'already exists' and succeeds."""
    store = tmp_path / ".db-wiki"
    runner.invoke(app, ["init", "--store-path", str(store)])
    result = runner.invoke(app, ["init", "--store-path", str(store)])
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()


def test_connect(tmp_path: Path):
    """connect saves connection_string to config.yaml after init."""
    store = tmp_path / ".db-wiki"
    runner.invoke(app, ["init", "--store-path", str(store)])

    conn_str = "Server=localhost;Database=test"
    result = runner.invoke(app, ["connect", conn_str, "--store-path", str(store)])
    assert result.exit_code == 0, result.output

    config_text = (store / "config.yaml").read_text(encoding="utf-8")
    assert "Server=localhost" in config_text


def test_connect_no_store(tmp_path: Path):
    """connect without prior init exits with code 1."""
    store = tmp_path / ".db-wiki"
    result = runner.invoke(app, ["connect", "Server=x;Database=y", "--store-path", str(store)])
    assert result.exit_code == 1


def test_ingest_no_file(tmp_path: Path):
    """ingest with a non-existent file exits with code 1 and shows error."""
    store = tmp_path / ".db-wiki"
    runner.invoke(app, ["init", "--store-path", str(store)])

    result = runner.invoke(app, ["ingest", "nonexistent.sql", "--store-path", str(store)])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()

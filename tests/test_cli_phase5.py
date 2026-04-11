"""Phase 5 CLI commands tests (CLI-05, EXPORT-01).

Tests verify the contracts for Phase 5 CLI implementations:
serve, status, export, daemon subcommands.
"""
import pytest


# ---------------------------------------------------------------------------
# EXPORT-01 / CLI-05: status command shows coverage
# ---------------------------------------------------------------------------


def test_status_command(tmp_path):
    """'db-wiki status' output contains 'Coverage'. (EXPORT-01, CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app
    from db_wiki.core.config import write_default_config
    from db_wiki.core.store import init_schema, open_store

    # Initialize a real store so the command succeeds
    write_default_config(tmp_path)
    conn = open_store(tmp_path / "knowledge.db")
    init_schema(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--store-path", str(tmp_path)])
    assert "Coverage" in result.output


# ---------------------------------------------------------------------------
# CLI-05: serve command is registered
# ---------------------------------------------------------------------------


def test_serve_command_exists():
    """'serve' command is registered in the Typer app. (CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output


# ---------------------------------------------------------------------------
# CLI-05: export command runs without error
# ---------------------------------------------------------------------------


def test_export_command(tmp_path):
    """'db-wiki export' runs without unhandled exceptions. (CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app
    from db_wiki.core.config import write_default_config
    from db_wiki.core.store import init_schema, open_store

    # Initialize a real store so the command can open the DB
    write_default_config(tmp_path)
    conn = open_store(tmp_path / "knowledge.db")
    init_schema(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["export", "--store-path", str(tmp_path), "--format", "markdown"],
    )
    # Exit 0 or a handled user-facing error (non-zero with message) is acceptable;
    # an unhandled exception (traceback in output) is not.
    assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# CLI-05: daemon subcommand group is registered and prints redirect message
# ---------------------------------------------------------------------------


def test_daemon_start_prints_redirect():
    """'db-wiki daemon start' prints redirect message to db-wiki serve. (CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app

    runner = CliRunner()
    result = runner.invoke(app, ["daemon", "start"])
    assert "serve" in result.output
    assert result.exit_code == 0


def test_daemon_stop_prints_redirect():
    """'db-wiki daemon stop' prints redirect message. (CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app

    runner = CliRunner()
    result = runner.invoke(app, ["daemon", "stop"])
    assert "serve" in result.output
    assert result.exit_code == 0


def test_daemon_status_prints_redirect():
    """'db-wiki daemon status' prints redirect message. (CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app

    runner = CliRunner()
    result = runner.invoke(app, ["daemon", "status"])
    assert "serve" in result.output
    assert result.exit_code == 0

"""Phase 5 Wave 0 test stubs for CLI Phase 5 commands (CLI-05, EXPORT-01).

All tests are marked xfail — they verify the contracts that the Phase 5
CLI implementation must satisfy.
"""
import pytest


XFAIL_REASON = "Phase 5 Wave 0 stub — not yet implemented"


# ---------------------------------------------------------------------------
# EXPORT-01 / CLI-05: status command shows coverage
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_status_command(tmp_path):
    """'db-wiki status' output contains 'Coverage'. (EXPORT-01, CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--store-path", str(tmp_path)])
    assert "Coverage" in result.output


# ---------------------------------------------------------------------------
# CLI-05: serve command is registered
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
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


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_export_command(tmp_path):
    """'db-wiki export' runs without unhandled exceptions. (CLI-05)"""
    from typer.testing import CliRunner

    from db_wiki.cli.app import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["export", "--store-path", str(tmp_path), "--format", "markdown"],
    )
    # Exit 0 or a handled user-facing error (non-zero with message) is acceptable;
    # an unhandled exception (traceback in output) is not.
    assert "Traceback" not in result.output

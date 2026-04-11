"""Tests for db_wiki/query/executor.py — live DB executor (QUERY-09)."""
from unittest.mock import MagicMock, patch

import pytest

from db_wiki.core.config import DBWikiConfig, DatabaseConfig, QueryConfig
from db_wiki.query.executor import execute_query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(connection_string=None, timeout_seconds=30, max_execution_rows=100):
    """Build a DBWikiConfig with the given database settings."""
    cfg = DBWikiConfig()
    cfg.database.connection_string = connection_string
    cfg.database.timeout_seconds = timeout_seconds
    cfg.query.max_execution_rows = max_execution_rows
    return cfg


# ---------------------------------------------------------------------------
# Non-SELECT rejection (T-04-06)
# ---------------------------------------------------------------------------


def test_execute_query_rejects_insert():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;")
    result = execute_query("INSERT INTO t VALUES (1)", cfg)
    assert result["success"] is False
    assert "SELECT" in result["error"]
    assert result["rows"] is None
    assert result["row_count"] == 0


def test_execute_query_rejects_delete():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;")
    result = execute_query("DELETE FROM t", cfg)
    assert result["success"] is False
    assert "SELECT" in result["error"]


def test_execute_query_rejects_drop():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;")
    result = execute_query("DROP TABLE t", cfg)
    assert result["success"] is False


def test_execute_query_rejects_empty_sql():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;")
    result = execute_query("", cfg)
    assert result["success"] is False
    assert "SELECT" in result["error"]


def test_execute_query_select_case_insensitive():
    """SELECT is accepted regardless of case — actual execution requires pyodbc."""
    cfg = _make_config()  # no connection string → will fail at connection check
    result = execute_query("select * from t", cfg)
    # Should fail at connection string check, not at SELECT validation
    assert "SELECT" not in (result["error"] or "")
    assert "connection" in result["error"].lower()


# ---------------------------------------------------------------------------
# Missing connection string
# ---------------------------------------------------------------------------


def test_execute_query_no_connection_string():
    cfg = _make_config(connection_string=None)
    result = execute_query("SELECT * FROM t", cfg)
    assert result["success"] is False
    assert "connection" in result["error"].lower()
    assert result["rows"] is None


# ---------------------------------------------------------------------------
# pyodbc not installed
# ---------------------------------------------------------------------------


def test_execute_query_pyodbc_not_installed():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;")
    with patch.dict("sys.modules", {"pyodbc": None}):
        result = execute_query("SELECT * FROM t", cfg)
    assert result["success"] is False
    assert "pyodbc" in result["error"]


# ---------------------------------------------------------------------------
# Successful execution via mocked pyodbc
# ---------------------------------------------------------------------------


def _mock_pyodbc_module(rows, columns):
    """Build a mock pyodbc module that returns rows for any query."""
    mock_cursor = MagicMock()
    mock_cursor.description = [(col, None, None, None, None, None, None) for col in columns]
    mock_cursor.fetchmany.return_value = rows

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pyodbc = MagicMock()
    mock_pyodbc.connect.return_value = mock_conn
    mock_pyodbc.Error = Exception  # so except clause works

    return mock_pyodbc


def test_execute_query_returns_list_of_dicts():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;", max_execution_rows=100)
    columns = ["id", "name"]
    rows = [(1, "Alice"), (2, "Bob")]

    mock_pyodbc = _mock_pyodbc_module(rows, columns)
    with patch.dict("sys.modules", {"pyodbc": mock_pyodbc}):
        result = execute_query("SELECT id, name FROM customers", cfg)

    assert result["success"] is True
    assert result["error"] is None
    assert result["row_count"] == 2
    assert result["rows"] == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


def test_execute_query_respects_max_rows():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;", max_execution_rows=2)
    columns = ["id"]
    rows = [(1,), (2,)]

    mock_pyodbc = _mock_pyodbc_module(rows, columns)
    with patch.dict("sys.modules", {"pyodbc": mock_pyodbc}):
        execute_query("SELECT id FROM t", cfg)

    # Verify fetchmany was called with the correct limit
    mock_conn = mock_pyodbc.connect.return_value
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchmany.assert_called_once_with(2)


def test_execute_query_pyodbc_error_returns_error_dict():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;")

    mock_pyodbc = MagicMock()
    mock_pyodbc.connect.side_effect = Exception("connection refused")
    mock_pyodbc.Error = Exception

    with patch.dict("sys.modules", {"pyodbc": mock_pyodbc}):
        result = execute_query("SELECT 1", cfg)

    assert result["success"] is False
    assert "connection refused" in result["error"]
    assert result["rows"] is None
    assert result["row_count"] == 0


def test_execute_query_closes_connection_on_success():
    cfg = _make_config(connection_string="Driver=SQL;Server=localhost;")
    columns = ["x"]
    rows = [(42,)]

    mock_pyodbc = _mock_pyodbc_module(rows, columns)
    with patch.dict("sys.modules", {"pyodbc": mock_pyodbc}):
        execute_query("SELECT x FROM t", cfg)

    mock_conn = mock_pyodbc.connect.return_value
    mock_conn.close.assert_called_once()

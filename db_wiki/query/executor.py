"""Optional live database executor for the NL-to-SQL pipeline.

Executes validated SELECT-only queries against a live SQL Server database via
pyodbc. pyodbc is a soft dependency — the executor returns a clear error if it
is not installed.

Security note (T-04-06): Only SELECT statements are allowed. Non-SELECT
statements are rejected before any database connection is attempted. Row count
is limited by config.query.max_execution_rows. Connection timeout is enforced
via config.database.timeout_seconds.

Security note (T-04-07): Pipeline does not execute SQL by default. Execution
requires explicit execute=True from the caller. Read-only safety is enforced
here by statement type check.
"""
from __future__ import annotations

import logging

import sqlglot
from sqlglot.errors import ParseError

logger = logging.getLogger(__name__)


def _is_safe_select(sql: str) -> bool:
    """Check that sql contains exactly one SELECT statement using AST parsing.

    Rejects multi-statement SQL, non-SELECT statements, CTEs wrapping
    destructive operations, and comment-prefixed bypasses.
    """
    if not sql or not sql.strip():
        return False
    try:
        statements = sqlglot.parse(sql, dialect="tsql")
    except ParseError:
        return False
    if len(statements) != 1:
        return False  # reject multi-statement (e.g. SELECT 1; DROP TABLE x)
    stmt = statements[0]
    if stmt is None:
        return False
    # Accept Select nodes (includes CTEs that resolve to SELECT)
    return isinstance(stmt, sqlglot.exp.Select)


def execute_query(sql: str, config) -> dict:
    """Execute a validated SELECT SQL query against the configured live database.

    Args:
        sql: The SQL query to execute. Must be a SELECT statement.
        config: DBWikiConfig instance with database and query config.

    Returns:
        Dict with keys:
          - success (bool): True if query executed successfully.
          - rows (list[dict] | None): Query result rows, or None on failure.
          - error (str | None): Error message string, or None on success.
          - row_count (int): Number of rows returned (0 on failure).
    """
    # T-04-06: Only SELECT statements can be executed (AST-based check)
    if not _is_safe_select(sql):
        return {
            "success": False,
            "rows": None,
            "error": "Only SELECT statements can be executed",
            "row_count": 0,
        }

    # Require a configured connection string
    connection_string = getattr(getattr(config, "database", None), "connection_string", None)
    if not connection_string:
        return {
            "success": False,
            "rows": None,
            "error": "No database connection configured",
            "row_count": 0,
        }

    # Soft dependency: pyodbc (optional install)
    try:
        import pyodbc  # noqa: F401 (lazy import)
    except ImportError:
        return {
            "success": False,
            "rows": None,
            "error": "pyodbc not installed. Install with: uv add pyodbc",
            "row_count": 0,
        }

    timeout_seconds = getattr(getattr(config, "database", None), "timeout_seconds", 30)
    max_rows = getattr(getattr(config, "query", None), "max_execution_rows", 100)

    try:
        import pyodbc as _pyodbc

        conn = _pyodbc.connect(connection_string, timeout=timeout_seconds)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            raw_rows = cursor.fetchmany(max_rows)

            # Convert rows to list[dict] using cursor.description for column names
            columns = [col[0] for col in cursor.description] if cursor.description else []
            rows = [dict(zip(columns, row)) for row in raw_rows]

            return {
                "success": True,
                "rows": rows,
                "error": None,
                "row_count": len(rows),
            }
        finally:
            conn.close()

    except Exception as exc:  # pyodbc.Error and any other DB errors
        logger.warning("Live query execution failed: %s", exc)
        return {
            "success": False,
            "rows": None,
            "error": str(exc),
            "row_count": 0,
        }

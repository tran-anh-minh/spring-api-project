"""SQL validator for the NL-to-SQL pipeline.

Validates generated SQL against the knowledge store schema using sqlglot's
qualify() optimizer to catch unknown tables and columns before execution.

Security note (T-04-04): All generated SQL must pass parse_one() + qualify()
before any execution. The validator catches schema violations but does NOT
verify that the statement is a SELECT — the executor (Plan 03) must check
statement type before executing.
"""
from __future__ import annotations

import logging
import sqlite3

import sqlglot
from sqlglot import optimizer
from sqlglot.errors import OptimizeError, ParseError

logger = logging.getLogger(__name__)


def build_schema_map(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """Build a schema map from the knowledge store for use with sqlglot qualify().

    Queries current_db_columns joined with current_db_tables to produce:
        {table_name: {column_name: data_type}}

    Args:
        conn: SQLite connection to the knowledge store (must have current_* views).

    Returns:
        Nested dict mapping table names to their column name -> data_type mappings.
        Returns an empty dict if no tables are found.
    """
    rows = conn.execute(
        """SELECT t.table_name, c.column_name, c.data_type
           FROM current_db_columns c
           JOIN current_db_tables t ON c.table_id = t.id
           ORDER BY t.table_name, c.ordinal_position, c.id"""
    ).fetchall()

    schema_map: dict[str, dict[str, str]] = {}
    for row in rows:
        table = row["table_name"]
        col = row["column_name"]
        dtype = row["data_type"] or "TEXT"
        if table not in schema_map:
            schema_map[table] = {}
        schema_map[table][col] = dtype

    return schema_map


def validate_sql(sql: str, schema_map: dict[str, dict[str, str]]) -> list[str]:
    """Validate SQL syntax and schema references using sqlglot.

    Performs two validation passes:
    1. sqlglot.parse_one() — catches syntax errors
    2. sqlglot.optimizer.qualify.qualify() — catches unknown tables/columns

    The original SQL string is preserved for error messages; qualify() output
    (which lowercases identifiers) is discarded after validation.

    Args:
        sql: The SQL string to validate.
        schema_map: Dict mapping table names to their column names and types.
            Built by build_schema_map() or constructed manually for tests.

    Returns:
        List of error message strings. Empty list means validation passed.
    """
    errors: list[str] = []

    if not sql or not sql.strip():
        errors.append("Syntax error: empty SQL statement")
        return errors

    # Pass 1: parse
    try:
        ast = sqlglot.parse_one(sql, dialect="tsql")
    except ParseError as e:
        errors.append(f"Syntax error: {e}")
        return errors
    except Exception as e:
        errors.append(f"Parse error: {e}")
        return errors

    if ast is None:
        errors.append("Syntax error: could not parse SQL statement")
        return errors

    # Pass 2: qualify (resolves column/table references against schema)
    try:
        optimizer.qualify.qualify(ast, schema=schema_map, dialect="tsql")
    except OptimizeError as e:
        errors.append(str(e))
    except Exception as e:
        # qualify() can raise various errors for unsupported constructs —
        # treat as a validation warning rather than a hard failure
        logger.debug("SQL qualify raised unexpected error: %s", e)
        errors.append(f"Validation error: {e}")

    return errors

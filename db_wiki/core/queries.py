"""Shared query helpers for entity lookup across server and CLI layers.

These functions provide a single source of truth for resolving entity names
and IDs from the knowledge store. Both db_wiki/server/app.py and
db_wiki/cli/app.py import from here to avoid duplicating lookup logic.
"""
import sqlite3


def lookup_entity_name(conn: sqlite3.Connection, entity_id: int) -> str:
    """Look up entity name by ID, checking tables first then procedures.

    Args:
        conn: SQLite connection with current_db_tables and current_db_procedures views.
        entity_id: The entity ID to look up.

    Returns:
        Entity name string, or "entity#{id}" if not found.
    """
    row = conn.execute(
        "SELECT table_name FROM current_db_tables WHERE id=?", (entity_id,)
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT procedure_name FROM current_db_procedures WHERE id=?", (entity_id,)
    ).fetchone()
    if row:
        return row[0]
    return f"entity#{entity_id}"


def find_entity_by_name(
    conn: sqlite3.Connection, entity_name: str
) -> tuple[int | None, str | None]:
    """Find entity ID and type by name, checking tables first then procedures.

    Args:
        conn: SQLite connection with current_db_tables and current_db_procedures views.
        entity_name: The entity name to search for.

    Returns:
        Tuple of (entity_id, entity_type) where entity_type is "table" or "procedure".
        Returns (None, None) if not found.
    """
    row = conn.execute(
        "SELECT id FROM current_db_tables WHERE table_name=?", (entity_name,)
    ).fetchone()
    if row:
        return row[0], "table"
    row = conn.execute(
        "SELECT id FROM current_db_procedures WHERE procedure_name=?", (entity_name,)
    ).fetchone()
    if row:
        return row[0], "procedure"
    return None, None

"""FTS5 full-text search index management (STORE-10).

The fts_entities virtual table is created by init_schema via schema.py.
This module manages populating and querying it.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def populate_fts(
    conn: sqlite3.Connection,
    entities: list[dict],  # [{"entity_name": "X", "description": "Y", "entity_type": "table", "entity_id": 1}]
) -> int:
    """Insert entities into fts_entities index. Returns count inserted."""
    count = 0
    for e in entities:
        conn.execute(
            "INSERT INTO fts_entities(entity_name, description, entity_type, entity_id) "
            "VALUES (?, ?, ?, ?)",
            (e["entity_name"], e.get("description", ""), e["entity_type"], e["entity_id"]),
        )
        count += 1
    conn.commit()
    return count


def populate_fts_from_store(conn: sqlite3.Connection) -> int:
    """Populate FTS index from current_db_tables and current_db_procedures.

    Reads each view once with correct column indexing:
    row[0]=id, row[1]=entity_name, row[2]=description.
    """
    entities: list[dict] = []
    # Tables: SELECT id, table_name, description
    for row in conn.execute("SELECT id, table_name, description FROM current_db_tables").fetchall():
        entities.append({
            "entity_name": row[1],
            "description": row[2] or "",
            "entity_type": "table",
            "entity_id": row[0],
        })
    # Procedures: SELECT id, procedure_name, description
    for row in conn.execute(
        "SELECT id, procedure_name, description FROM current_db_procedures"
    ).fetchall():
        entities.append({
            "entity_name": row[1],
            "description": row[2] or "",
            "entity_type": "procedure",
            "entity_id": row[0],
        })
    # Clear existing and repopulate
    conn.execute("DELETE FROM fts_entities")
    return populate_fts(conn, entities)


def sync_fts(conn: sqlite3.Connection) -> int:
    """Clear and repopulate FTS index from store."""
    return populate_fts_from_store(conn)


def search_fts(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> list[tuple[str, str, int, float]]:
    """Search fts_entities. Returns (entity_type, entity_name, entity_id, rank).

    FTS5 rank() returns negative values (less negative = better match).
    """
    rows = conn.execute(
        "SELECT entity_type, entity_name, entity_id, rank "
        "FROM fts_entities WHERE fts_entities MATCH ? "
        "ORDER BY rank LIMIT ?",
        (query, limit),
    ).fetchall()
    return [(row[0], row[1], row[2], row[3]) for row in rows]

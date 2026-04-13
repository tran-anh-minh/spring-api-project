"""SQLite connection management for the db-wiki knowledge store.

Security note (T-01-01): db_path is resolved to absolute before connecting
to prevent path traversal attacks via user-supplied --store-path arguments.

Security note (T-02-01): load_extension is disabled immediately after loading
sqlite_vec to prevent further extension loading.
"""
import sqlite3
from pathlib import Path

import sqlite_vec

from db_wiki.core.schema import get_schema_sql
from db_wiki.learning.schema_ext import init_learning_schema


def open_store(db_path: Path) -> sqlite3.Connection:
    """Open the SQLite knowledge store at *db_path*.

    Applies:
    - ``PRAGMA journal_mode=WAL`` — concurrent readers + single writer
    - ``PRAGMA foreign_keys=ON`` — enforce referential integrity
    - ``conn.row_factory = sqlite3.Row`` — column-name access on rows

    Security: *db_path* is resolved to an absolute path before connecting
    (T-01-01 mitigation for path traversal via ``--store-path``).
    """
    abs_path = Path(db_path).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(abs_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    # Load sqlite-vec extension for vector similarity search (T-02-01)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Execute all DDL statements to create tables, views, and indexes.

    Safe to call on an existing database — all statements use
    ``CREATE TABLE IF NOT EXISTS`` / ``CREATE VIEW IF NOT EXISTS``.

    Args:
        conn: An open SQLite connection (from :func:`open_store` or test fixtures).
    """
    conn.executescript(get_schema_sql())
    init_learning_schema(conn)


def init_vec_table(conn: sqlite3.Connection, dimensions: int) -> None:
    """Create sqlite-vec virtual table for the given embedding dimensions.

    Per D-07/D-19: unified table with entity_type + entity_id columns.
    Called when embedding is first needed, not during init_schema.

    Args:
        conn: An open SQLite connection with sqlite-vec loaded.
        dimensions: Embedding vector size (e.g. 384, 1536).
    """
    table_name = f"vec_embeddings_{dimensions}"
    exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()[0]
    if exists:
        return
    conn.execute(
        f"CREATE VIRTUAL TABLE {table_name} USING vec0("
        f"    entity_type TEXT,"
        f"    entity_id INTEGER,"
        f"    embedding FLOAT[{dimensions}]"
        f")"
    )

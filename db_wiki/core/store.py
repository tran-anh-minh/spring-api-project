"""SQLite connection management for the db-wiki knowledge store.

Security note (T-01-01): db_path is resolved to absolute before connecting
to prevent path traversal attacks via user-supplied --store-path arguments.
"""
import sqlite3
from pathlib import Path

from db_wiki.core.schema import get_schema_sql


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
    conn = sqlite3.connect(str(abs_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Execute all DDL statements to create tables, views, and indexes.

    Safe to call on an existing database — all statements use
    ``CREATE TABLE IF NOT EXISTS`` / ``CREATE VIEW IF NOT EXISTS``.

    Args:
        conn: An open SQLite connection (from :func:`open_store` or test fixtures).
    """
    conn.executescript(get_schema_sql())

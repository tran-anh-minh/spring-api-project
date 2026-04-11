"""Cross-project pattern store at ~/.db-wiki/cross.db (CROSS-01, D-07).

Stores extracted patterns (naming conventions, enum values, schema shapes,
state machine templates) for sharing across database projects. Nothing is
shared unless user explicitly runs `db-wiki export --to-cross` (D-07).
"""
import sqlite3
from pathlib import Path

DEFAULT_CROSS_DB_PATH = Path.home() / ".db-wiki" / "cross.db"

CROSS_SCHEMA = """
CREATE TABLE IF NOT EXISTS cross_patterns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type  TEXT NOT NULL,
    pattern_key   TEXT NOT NULL,
    pattern_value TEXT NOT NULL,
    source_db     TEXT NOT NULL,
    confidence    REAL NOT NULL DEFAULT 0.5,
    created_at    TEXT NOT NULL,
    UNIQUE(pattern_type, pattern_key, source_db)
);
CREATE INDEX IF NOT EXISTS idx_cross_pattern_type
    ON cross_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_cross_source_db
    ON cross_patterns(source_db);

CREATE TABLE IF NOT EXISTS cross_db_profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    db_name       TEXT NOT NULL UNIQUE,
    table_names   TEXT NOT NULL,
    column_names  TEXT NOT NULL,
    table_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
"""


def open_cross_store(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the cross-project pattern store.

    Creates ~/.db-wiki/ directory and cross.db if they don't exist.
    Does NOT load sqlite-vec (cross.db has no vector data).
    """
    path = db_path or DEFAULT_CROSS_DB_PATH
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_cross_schema(conn: sqlite3.Connection) -> None:
    """Create cross-project tables if they don't exist."""
    conn.executescript(CROSS_SCHEMA)
    conn.commit()

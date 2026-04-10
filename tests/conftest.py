import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_store_path(tmp_path: Path) -> Path:
    """Return a temporary directory path for a knowledge store."""
    store_dir = tmp_path / ".db-wiki"
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir


@pytest.fixture
def in_memory_db():
    """Yield an in-memory SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def initialized_db(in_memory_db: sqlite3.Connection) -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the full schema initialized."""
    from db_wiki.core.store import init_schema

    init_schema(in_memory_db)
    return in_memory_db

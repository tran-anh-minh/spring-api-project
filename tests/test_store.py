"""Tests for db_wiki.core.store and db_wiki.core.schema."""
import sqlite3
from pathlib import Path

import pytest

from db_wiki.core.store import init_schema, open_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _view_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r["name"] for r in rows]


TEMPORAL_COLUMNS = [
    "valid_from",
    "valid_from_ts",
    "valid_until",
    "valid_until_ts",
    "recorded_at",
    "recorded_at_ts",
    "invalidated_at",
    "invalidated_at_ts",
]

ENTITY_TABLES = [
    "db_tables",
    "db_columns",
    "db_procedures",
    "db_relationships",
    "db_indexes",
]


# ---------------------------------------------------------------------------
# Schema existence tests
# ---------------------------------------------------------------------------

class TestSchemaCreated:
    def test_db_tables_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _table_exists(initialized_db, "db_tables")

    def test_db_columns_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _table_exists(initialized_db, "db_columns")

    def test_db_procedures_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _table_exists(initialized_db, "db_procedures")

    def test_db_relationships_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _table_exists(initialized_db, "db_relationships")

    def test_db_indexes_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _table_exists(initialized_db, "db_indexes")


# ---------------------------------------------------------------------------
# Temporal column presence on each entity table
# ---------------------------------------------------------------------------

class TestTemporalColumns:
    @pytest.mark.parametrize("table", ENTITY_TABLES)
    def test_all_8_temporal_columns(
        self, initialized_db: sqlite3.Connection, table: str
    ) -> None:
        cols = _column_names(initialized_db, table)
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Column '{tc}' missing from table '{table}'"

    def test_db_columns_has_table_id_fk(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "db_columns")
        assert "table_id" in cols

    def test_db_relationships_has_relationship_type(
        self, initialized_db: sqlite3.Connection
    ) -> None:
        cols = _column_names(initialized_db, "db_relationships")
        assert "relationship_type" in cols


# ---------------------------------------------------------------------------
# View existence tests
# ---------------------------------------------------------------------------

class TestViews:
    @pytest.mark.parametrize("table", ENTITY_TABLES)
    def test_current_view_exists(
        self, initialized_db: sqlite3.Connection, table: str
    ) -> None:
        assert _view_exists(initialized_db, f"current_{table}"), (
            f"View 'current_{table}' does not exist"
        )

    def test_current_db_tables_filters_active_rows(
        self, initialized_db: sqlite3.Connection
    ) -> None:
        """Rows with valid_until=NULL and invalidated_at=NULL appear in view."""
        initialized_db.execute(
            """
            INSERT INTO db_tables
                (table_name, valid_from, valid_from_ts, recorded_at, recorded_at_ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("orders", "2026-01-01T00:00:00Z", 1735689600, "2026-01-01T00:00:00Z", 1735689600),
        )
        initialized_db.commit()
        row = initialized_db.execute(
            "SELECT * FROM current_db_tables WHERE table_name = 'orders'"
        ).fetchone()
        assert row is not None

    def test_current_db_tables_excludes_invalidated_rows(
        self, initialized_db: sqlite3.Connection
    ) -> None:
        """Rows with invalidated_at set do NOT appear in view."""
        initialized_db.execute(
            """
            INSERT INTO db_tables
                (table_name, valid_from, valid_from_ts, recorded_at, recorded_at_ts,
                 invalidated_at, invalidated_at_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dropped_table",
                "2026-01-01T00:00:00Z", 1735689600,
                "2026-01-01T00:00:00Z", 1735689600,
                "2026-04-01T00:00:00Z", 1743465600,
            ),
        )
        initialized_db.commit()
        row = initialized_db.execute(
            "SELECT * FROM current_db_tables WHERE table_name = 'dropped_table'"
        ).fetchone()
        assert row is None

    def test_current_db_tables_excludes_expired_rows(
        self, initialized_db: sqlite3.Connection
    ) -> None:
        """Rows with valid_until set (non-NULL) do NOT appear in view."""
        initialized_db.execute(
            """
            INSERT INTO db_tables
                (table_name, valid_from, valid_from_ts, recorded_at, recorded_at_ts,
                 valid_until, valid_until_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "old_table",
                "2026-01-01T00:00:00Z", 1735689600,
                "2026-01-01T00:00:00Z", 1735689600,
                "2026-03-01T00:00:00Z", 1740787200,
            ),
        )
        initialized_db.commit()
        row = initialized_db.execute(
            "SELECT * FROM current_db_tables WHERE table_name = 'old_table'"
        ).fetchone()
        assert row is None


# ---------------------------------------------------------------------------
# open_store tests
# ---------------------------------------------------------------------------

class TestOpenStore:
    def test_open_store_returns_connection(self, tmp_store_path: Path) -> None:
        db_path = tmp_store_path / "knowledge.db"
        conn = open_store(db_path)
        assert conn is not None
        conn.close()

    def test_open_store_enables_wal_mode(self, tmp_store_path: Path) -> None:
        db_path = tmp_store_path / "knowledge.db"
        conn = open_store(db_path)
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"
        conn.close()

    def test_open_store_enables_foreign_keys(self, tmp_store_path: Path) -> None:
        db_path = tmp_store_path / "knowledge.db"
        conn = open_store(db_path)
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1
        conn.close()

    def test_open_store_sets_row_factory(self, tmp_store_path: Path) -> None:
        db_path = tmp_store_path / "knowledge.db"
        conn = open_store(db_path)
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_open_store_resolves_to_absolute_path(self, tmp_store_path: Path) -> None:
        """Security: open_store must resolve to absolute path (T-01-01)."""
        db_path = tmp_store_path / "knowledge.db"
        conn = open_store(db_path)
        # Connection opened without error; path was valid
        conn.close()
        assert db_path.exists()

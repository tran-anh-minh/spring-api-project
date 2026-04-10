"""Tests for Phase 2 schema tables, views, and config extensions."""
import sqlite3

import pytest

from db_wiki.core.store import init_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _real_table_exists(conn: sqlite3.Connection, name: str) -> bool:
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
    return [r[1] for r in rows]


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

PHASE2_TABLES = [
    "sp_branches",
    "sp_reliability",
    "sp_call_chains",
    "enum_values",
    "state_transitions",
    "bitmask_definitions",
    "column_aliases",
]


@pytest.fixture
def initialized_db():
    """In-memory SQLite with full schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Test 1: sp_branches table
# ---------------------------------------------------------------------------

class TestSpBranches:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _real_table_exists(initialized_db, "sp_branches")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "sp_branches")
        for expected in [
            "id", "procedure_id", "branch_index", "condition_text",
            "branch_type", "tables_touched_json", "nesting_depth",
        ]:
            assert expected in cols, f"Missing column {expected}"
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Missing temporal column {tc}"


# ---------------------------------------------------------------------------
# Test 2: sp_reliability table
# ---------------------------------------------------------------------------

class TestSpReliability:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _real_table_exists(initialized_db, "sp_reliability")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "sp_reliability")
        for expected in [
            "id", "procedure_id", "parse_quality", "is_degraded",
            "has_dynamic_sql", "has_cycle", "partial_ast",
            "dynamic_sql_locations_json",
        ]:
            assert expected in cols, f"Missing column {expected}"
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Missing temporal column {tc}"


# ---------------------------------------------------------------------------
# Test 3: sp_call_chains table
# ---------------------------------------------------------------------------

class TestSpCallChains:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _real_table_exists(initialized_db, "sp_call_chains")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "sp_call_chains")
        for expected in [
            "id", "caller_id", "callee_id", "callee_name_raw",
            "callee_schema", "is_resolved",
        ]:
            assert expected in cols, f"Missing column {expected}"
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Missing temporal column {tc}"


# ---------------------------------------------------------------------------
# Test 4: enum_values table
# ---------------------------------------------------------------------------

class TestEnumValues:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _real_table_exists(initialized_db, "enum_values")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "enum_values")
        for expected in [
            "id", "table_name", "column_name", "enum_value", "enum_label",
            "confidence", "detection_method", "source_procedure_id",
        ]:
            assert expected in cols, f"Missing column {expected}"
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Missing temporal column {tc}"


# ---------------------------------------------------------------------------
# Test 5: state_transitions table
# ---------------------------------------------------------------------------

class TestStateTransitions:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _real_table_exists(initialized_db, "state_transitions")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "state_transitions")
        for expected in [
            "id", "table_name", "column_name", "from_value", "to_value",
            "confidence", "source_procedure_id",
        ]:
            assert expected in cols, f"Missing column {expected}"
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Missing temporal column {tc}"


# ---------------------------------------------------------------------------
# Test 6: bitmask_definitions table
# ---------------------------------------------------------------------------

class TestBitmaskDefinitions:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _real_table_exists(initialized_db, "bitmask_definitions")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "bitmask_definitions")
        for expected in [
            "id", "table_name", "column_name", "bit_position", "bit_label",
            "confidence", "detection_method", "source_procedure_id",
        ]:
            assert expected in cols, f"Missing column {expected}"
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Missing temporal column {tc}"


# ---------------------------------------------------------------------------
# Test 7: column_aliases table
# ---------------------------------------------------------------------------

class TestColumnAliases:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _real_table_exists(initialized_db, "column_aliases")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        cols = _column_names(initialized_db, "column_aliases")
        for expected in [
            "id", "table_name", "column_name", "alias",
            "confidence", "source_procedure_id",
        ]:
            assert expected in cols, f"Missing column {expected}"
        for tc in TEMPORAL_COLUMNS:
            assert tc in cols, f"Missing temporal column {tc}"


# ---------------------------------------------------------------------------
# Test 8: fts_entities virtual table
# ---------------------------------------------------------------------------

class TestFtsEntities:
    def test_table_exists(self, initialized_db: sqlite3.Connection) -> None:
        assert _table_exists(initialized_db, "fts_entities")

    def test_columns(self, initialized_db: sqlite3.Connection) -> None:
        # FTS5 tables can be queried but PRAGMA table_info doesn't work,
        # so we insert and select to verify column names
        initialized_db.execute(
            "INSERT INTO fts_entities(entity_name, description, entity_type, entity_id) "
            "VALUES (?, ?, ?, ?)",
            ("Orders", "Main order table", "table", "1"),
        )
        row = initialized_db.execute(
            "SELECT entity_name, description, entity_type, entity_id "
            "FROM fts_entities WHERE fts_entities MATCH 'Orders'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Orders"


# ---------------------------------------------------------------------------
# Test 9: current_* views exist and filter correctly
# ---------------------------------------------------------------------------

class TestPhase2Views:
    @pytest.mark.parametrize("table", PHASE2_TABLES)
    def test_current_view_exists(
        self, initialized_db: sqlite3.Connection, table: str
    ) -> None:
        assert _view_exists(initialized_db, f"current_{table}"), (
            f"View 'current_{table}' does not exist"
        )

    def test_current_sp_branches_filters_active(
        self, initialized_db: sqlite3.Connection
    ) -> None:
        # Insert a procedure first (FK reference)
        initialized_db.execute(
            "INSERT INTO db_procedures "
            "(procedure_name, valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("sp_test", "2026-01-01", 1735689600, "2026-01-01", 1735689600),
        )
        proc_id = initialized_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Active row
        initialized_db.execute(
            "INSERT INTO sp_branches "
            "(procedure_id, branch_index, branch_type, nesting_depth, "
            " valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (proc_id, 0, "if", 0, "2026-01-01", 1735689600, "2026-01-01", 1735689600),
        )

        # Invalidated row
        initialized_db.execute(
            "INSERT INTO sp_branches "
            "(procedure_id, branch_index, branch_type, nesting_depth, "
            " valid_from, valid_from_ts, recorded_at, recorded_at_ts, "
            " invalidated_at, invalidated_at_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (proc_id, 1, "else", 0, "2026-01-01", 1735689600, "2026-01-01", 1735689600,
             "2026-04-01", 1743465600),
        )
        initialized_db.commit()

        rows = initialized_db.execute("SELECT * FROM current_sp_branches").fetchall()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Test 10 & 11: EmbeddingConfig
# ---------------------------------------------------------------------------

class TestEmbeddingConfig:
    def test_embedding_config_defaults(self) -> None:
        from db_wiki.core.config import EmbeddingConfig

        cfg = EmbeddingConfig()
        assert cfg.provider == "local"
        assert cfg.model_name == "all-MiniLM-L6-v2"
        assert cfg.dimensions == 384

    def test_dbwiki_config_has_embedding(self) -> None:
        from db_wiki.core.config import DBWikiConfig, EmbeddingConfig

        cfg = DBWikiConfig()
        assert isinstance(cfg.embedding, EmbeddingConfig)
        assert cfg.embedding.provider == "local"

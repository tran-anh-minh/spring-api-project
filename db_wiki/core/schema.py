"""SQLite DDL for the db-wiki knowledge store.

All entity tables follow the bi-temporal model (D-01/D-02):
  - valid_from / valid_from_ts: when the fact became true in the real world
  - valid_until / valid_until_ts: when the fact ceased to be true (NULL = still valid)
  - recorded_at / recorded_at_ts: when db-wiki first learned the fact
  - invalidated_at / invalidated_at_ts: when db-wiki marked the fact as no longer current

Application code MUST query through current_* views, never raw tables (STORE-02).
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS db_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name      TEXT NOT NULL,
    schema_name     TEXT,
    description     TEXT,
    row_count       INTEGER,
    -- bi-temporal columns (D-01 / D-02)
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_db_tables_valid_from_ts
    ON db_tables(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_db_tables_recorded_at_ts
    ON db_tables(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_db_tables AS
SELECT * FROM db_tables
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_columns (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id            INTEGER NOT NULL REFERENCES db_tables(id),
    column_name         TEXT NOT NULL,
    data_type           TEXT,
    is_nullable         INTEGER NOT NULL DEFAULT 1,
    is_primary_key      INTEGER NOT NULL DEFAULT 0,
    is_unique           INTEGER NOT NULL DEFAULT 0,
    default_value       TEXT,
    description         TEXT,
    ordinal_position    INTEGER,
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_db_columns_valid_from_ts
    ON db_columns(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_db_columns_recorded_at_ts
    ON db_columns(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_db_columns AS
SELECT * FROM db_columns
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_procedures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_name  TEXT NOT NULL,
    schema_name     TEXT,
    description     TEXT,
    body_hash       TEXT,
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_db_procedures_valid_from_ts
    ON db_procedures(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_db_procedures_recorded_at_ts
    ON db_procedures(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_db_procedures AS
SELECT * FROM db_procedures
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_relationships (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           INTEGER NOT NULL,
    target_id           INTEGER,          -- NULL when target entity unresolved
    relationship_type   TEXT NOT NULL,   -- fk_declared|fk_inferred|joins_with|reads_from|writes_to|feeds_into
    source_column       TEXT,
    target_column       TEXT,
    confidence          REAL NOT NULL DEFAULT 1.0,
    evidence            TEXT,
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_db_relationships_valid_from_ts
    ON db_relationships(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_db_relationships_recorded_at_ts
    ON db_relationships(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_db_relationships AS
SELECT * FROM db_relationships
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_indexes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id        INTEGER NOT NULL REFERENCES db_tables(id),
    index_name      TEXT NOT NULL,
    is_unique       INTEGER NOT NULL DEFAULT 0,
    columns_json    TEXT NOT NULL,   -- JSON array of column names
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_db_indexes_valid_from_ts
    ON db_indexes(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_db_indexes_recorded_at_ts
    ON db_indexes(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_db_indexes AS
SELECT * FROM db_indexes
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ===========================================================================
-- Phase 2: SP Intelligence Tables (STORE-05, STORE-06, D-18)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS sp_branches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id        INTEGER NOT NULL REFERENCES db_procedures(id),
    branch_index        INTEGER NOT NULL,
    condition_text      TEXT,
    branch_type         TEXT NOT NULL,   -- 'if', 'else', 'case_when', 'while'
    tables_touched_json TEXT,            -- JSON array of table names
    nesting_depth       INTEGER NOT NULL DEFAULT 0,
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sp_branches_valid_from_ts
    ON sp_branches(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_sp_branches_recorded_at_ts
    ON sp_branches(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_sp_branches AS
SELECT * FROM sp_branches
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sp_reliability (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id                INTEGER NOT NULL REFERENCES db_procedures(id),
    parse_quality               REAL NOT NULL DEFAULT 1.0,
    is_degraded                 INTEGER NOT NULL DEFAULT 0,
    has_dynamic_sql             INTEGER NOT NULL DEFAULT 0,
    has_cycle                   INTEGER NOT NULL DEFAULT 0,
    partial_ast                 INTEGER NOT NULL DEFAULT 0,
    dynamic_sql_locations_json  TEXT,
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sp_reliability_valid_from_ts
    ON sp_reliability(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_sp_reliability_recorded_at_ts
    ON sp_reliability(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_sp_reliability AS
SELECT * FROM sp_reliability
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sp_call_chains (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_id           INTEGER NOT NULL REFERENCES db_procedures(id),
    callee_id           INTEGER,         -- NULL if unresolved (D-16)
    callee_name_raw     TEXT NOT NULL,
    callee_schema       TEXT,
    is_resolved         INTEGER NOT NULL DEFAULT 0,
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sp_call_chains_valid_from_ts
    ON sp_call_chains(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_sp_call_chains_recorded_at_ts
    ON sp_call_chains(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_sp_call_chains AS
SELECT * FROM sp_call_chains
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS enum_values (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name          TEXT NOT NULL,
    column_name         TEXT NOT NULL,
    enum_value          TEXT NOT NULL,
    enum_label          TEXT,
    confidence          REAL NOT NULL DEFAULT 0.5,
    detection_method    TEXT NOT NULL,   -- 'case_when', 'sp_name_heuristic', 'column_name_heuristic'
    source_procedure_id INTEGER REFERENCES db_procedures(id),
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_enum_values_valid_from_ts
    ON enum_values(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_enum_values_recorded_at_ts
    ON enum_values(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_enum_values AS
SELECT * FROM enum_values
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS state_transitions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name          TEXT NOT NULL,
    column_name         TEXT NOT NULL,
    from_value          TEXT NOT NULL,
    to_value            TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.9,
    source_procedure_id INTEGER REFERENCES db_procedures(id),
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_state_transitions_valid_from_ts
    ON state_transitions(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_state_transitions_recorded_at_ts
    ON state_transitions(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_state_transitions AS
SELECT * FROM state_transitions
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bitmask_definitions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name          TEXT NOT NULL,
    column_name         TEXT NOT NULL,
    bit_position        INTEGER NOT NULL,
    bit_label           TEXT,
    confidence          REAL NOT NULL DEFAULT 0.3,
    detection_method    TEXT NOT NULL,
    source_procedure_id INTEGER REFERENCES db_procedures(id),
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_bitmask_definitions_valid_from_ts
    ON bitmask_definitions(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_bitmask_definitions_recorded_at_ts
    ON bitmask_definitions(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_bitmask_definitions AS
SELECT * FROM bitmask_definitions
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS column_aliases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name          TEXT NOT NULL,
    column_name         TEXT NOT NULL,
    alias               TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.5,
    source_procedure_id INTEGER REFERENCES db_procedures(id),
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_column_aliases_valid_from_ts
    ON column_aliases(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_column_aliases_recorded_at_ts
    ON column_aliases(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_column_aliases AS
SELECT * FROM column_aliases
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ===========================================================================
-- Phase 2: Full-Text Search (STORE-10)
-- ===========================================================================

CREATE VIRTUAL TABLE IF NOT EXISTS fts_entities USING fts5(
    entity_name,
    description,
    entity_type UNINDEXED,
    entity_id UNINDEXED,
    tokenize='porter ascii'
);
"""


def get_schema_sql() -> str:
    """Return the full DDL string for schema initialization."""
    return SCHEMA_SQL

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
    target_id           INTEGER NOT NULL,
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
"""


def get_schema_sql() -> str:
    """Return the full DDL string for schema initialization."""
    return SCHEMA_SQL

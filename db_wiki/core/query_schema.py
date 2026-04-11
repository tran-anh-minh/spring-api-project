"""SQLite DDL for Phase 4 query engine tables.

Extends the base schema with:
  - wiki_pages: cached on-demand wiki content (L0/L1/L2 tiers)
  - derived_metrics: user-defined SQL expression → business concept mappings
  - query_cache: cached NL→SQL query results keyed by question hash

wiki_pages and derived_metrics follow the bi-temporal model (same as Phase 1).
query_cache is a pure LRU cache (no bi-temporal tracking needed).
"""

QUERY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS wiki_pages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL,
    entity_id       INTEGER NOT NULL,
    tier            TEXT NOT NULL,          -- 'L0' | 'L1' | 'L2'
    content         TEXT NOT NULL,
    schema_version  INTEGER NOT NULL,
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_wiki_pages_current
    ON wiki_pages (entity_type, entity_id, tier)
    WHERE valid_until IS NULL AND invalidated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_wiki_pages_valid_from_ts
    ON wiki_pages(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_recorded_at_ts
    ON wiki_pages(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_wiki_pages AS
SELECT * FROM wiki_pages
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS derived_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name     TEXT NOT NULL,
    sql_fragment    TEXT NOT NULL,
    source_tables   TEXT,                   -- JSON array of table name strings
    description     TEXT,
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_derived_metrics_current
    ON derived_metrics (metric_name)
    WHERE valid_until IS NULL AND invalidated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_derived_metrics_valid_from_ts
    ON derived_metrics(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_derived_metrics_recorded_at_ts
    ON derived_metrics(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_derived_metrics AS
SELECT * FROM derived_metrics
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS query_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question_hash   TEXT NOT NULL UNIQUE,
    question        TEXT NOT NULL,
    sql             TEXT NOT NULL,
    tier            TEXT NOT NULL,
    schema_version  INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    created_at_ts   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_cache_schema_version
    ON query_cache(schema_version);
"""


def get_query_schema_sql() -> str:
    """Return the full DDL string for Phase 4 query engine schema initialization."""
    return QUERY_SCHEMA_SQL


def init_query_schema(conn) -> None:
    """Execute all Phase 4 DDL statements (tables, views, indexes).

    Safe to call on an existing database — all statements use
    ``CREATE TABLE IF NOT EXISTS`` / ``CREATE VIEW IF NOT EXISTS``.

    Args:
        conn: An open SQLite connection (from open_store() or test fixtures).
    """
    conn.executescript(QUERY_SCHEMA_SQL)

"""SQLite DDL extension for Phase 3 learning loop tables.

Extends the core schema (db_wiki/core/schema.py) with three new bi-temporal
tables for knowledge gap tracking and agent coordination.

All tables follow the same bi-temporal pattern as Phase 1-2 tables:
  - valid_from / valid_from_ts: when the gap/task/result became active
  - valid_until / valid_until_ts: when it was superseded (NULL = current)
  - recorded_at / recorded_at_ts: when db-wiki first recorded this row
  - invalidated_at / invalidated_at_ts: when it was hard-deleted (NULL = live)

Application code MUST query through current_* views (STORE-02).
"""

import sqlite3

LEARNING_SCHEMA_SQL = """
-- ============================================================
-- knowledge_gaps: tracks what the system doesn't know yet
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_type            TEXT NOT NULL,           -- e.g. "missing_docs", "unresolved_relationship"
    entity_type         TEXT NOT NULL,           -- "table", "column", "sp", "relationship"
    entity_id           INTEGER,                 -- FK to the entity (nullable for system-level gaps)
    entity_name         TEXT NOT NULL,           -- human-readable name for display
    description         TEXT,                    -- optional detail about what is unknown
    severity            REAL NOT NULL DEFAULT 0.5,       -- 0.0-1.0, higher = more critical
    priority_score      REAL NOT NULL DEFAULT 0.0,       -- computed: severity * weights
    status              TEXT NOT NULL DEFAULT 'open',    -- open|investigating|resolved|permanent
    attempt_count       INTEGER NOT NULL DEFAULT 0,      -- number of investigation attempts
    cooldown_until      TEXT,                    -- ISO timestamp when cooldown expires
    cooldown_until_ts   INTEGER,                 -- epoch seconds
    last_attempt_at     TEXT,                    -- ISO timestamp of last investigation
    last_attempt_at_ts  INTEGER,                 -- epoch seconds
    resolution_notes    TEXT,                    -- explanation when status=resolved|permanent
    human_confirmed     INTEGER NOT NULL DEFAULT 0,      -- 1 if a human has verified this gap
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

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_status
    ON knowledge_gaps (status);

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_priority
    ON knowledge_gaps (priority_score DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_type_entity
    ON knowledge_gaps (gap_type, entity_name);

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_valid_from_ts
    ON knowledge_gaps (valid_from_ts);

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_recorded_at_ts
    ON knowledge_gaps (recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_knowledge_gaps AS
SELECT * FROM knowledge_gaps
WHERE valid_until IS NULL AND invalidated_at IS NULL;

-- ============================================================
-- agent_tasks: work items assigned to learning agents
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_id      INTEGER NOT NULL REFERENCES knowledge_gaps(id),
    agent_type  TEXT NOT NULL,              -- research|review|collector
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|failed
    input_json  TEXT,                       -- JSON blob of agent input parameters
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

CREATE INDEX IF NOT EXISTS idx_agent_tasks_gap_id
    ON agent_tasks (gap_id);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_status
    ON agent_tasks (status);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_valid_from_ts
    ON agent_tasks (valid_from_ts);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_recorded_at_ts
    ON agent_tasks (recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_agent_tasks AS
SELECT * FROM agent_tasks
WHERE valid_until IS NULL AND invalidated_at IS NULL;

-- ============================================================
-- agent_results: findings produced by agents for tasks
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES agent_tasks(id),
    agent_type      TEXT NOT NULL,              -- research|review|collector
    success         INTEGER NOT NULL DEFAULT 0, -- 1=success, 0=failure
    findings_json   TEXT,                       -- JSON blob of structured findings
    rationale       TEXT,                       -- free-text explanation
    approved        INTEGER,                    -- NULL=pending, 1=approved, 0=rejected
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

CREATE INDEX IF NOT EXISTS idx_agent_results_task_id
    ON agent_results (task_id);

CREATE INDEX IF NOT EXISTS idx_agent_results_valid_from_ts
    ON agent_results (valid_from_ts);

CREATE INDEX IF NOT EXISTS idx_agent_results_recorded_at_ts
    ON agent_results (recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_agent_results AS
SELECT * FROM agent_results
WHERE valid_until IS NULL AND invalidated_at IS NULL;
"""


def init_learning_schema(conn: sqlite3.Connection) -> None:
    """Execute all learning loop DDL statements.

    Creates knowledge_gaps, agent_tasks, agent_results tables plus their
    current_* views and indexes. Safe to call on an existing database —
    all statements use CREATE TABLE/VIEW IF NOT EXISTS.

    Args:
        conn: An open SQLite connection (from open_store or test fixtures).
    """
    conn.executescript(LEARNING_SCHEMA_SQL)

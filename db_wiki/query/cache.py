"""NL-to-SQL query cache with schema version invalidation.

Caches NL question → SQL mappings in the query_cache table (defined in
query_schema.py). Cache entries are keyed by a SHA-256 hash of the question
and invalidated when the schema version changes.

Security note (T-04-08): Cache is local SQLite — same trust boundary as
knowledge store. A poisoned cache entry would return wrong SQL but cannot
execute without explicit execute=True. Cache cleared on schema version change.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def compute_question_hash(question: str) -> str:
    """Compute a stable SHA-256 hash of a normalised question string.

    Normalisation: strip whitespace, lowercase.

    Args:
        question: The natural language question.

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()


def get_cached_query(
    conn: sqlite3.Connection,
    question_hash: str,
    current_schema_version: int,
) -> str | None:
    """Return cached SQL for a question hash if the schema version matches.

    Args:
        conn: SQLite connection with query_cache table.
        question_hash: SHA-256 hex hash of the question (from compute_question_hash).
        current_schema_version: Current schema version from get_schema_version().

    Returns:
        Cached SQL string if found and schema version matches, else None.
    """
    row = conn.execute(
        "SELECT sql FROM query_cache WHERE question_hash = ? AND schema_version = ?",
        (question_hash, current_schema_version),
    ).fetchone()
    if row is None:
        return None
    return row[0] if isinstance(row, (tuple, list)) else row["sql"]


def cache_query(
    conn: sqlite3.Connection,
    question: str,
    question_hash: str,
    sql: str,
    tier: str,
    schema_version: int,
) -> None:
    """Insert or replace a cached NL → SQL mapping.

    Uses INSERT OR REPLACE to handle duplicate question hashes gracefully.

    Args:
        conn: SQLite connection with query_cache table.
        question: The original natural language question.
        question_hash: SHA-256 hex hash of the question.
        sql: The generated SQL string to cache.
        tier: Query tier string (e.g. "lookup", "aggregation").
        schema_version: Current schema version (from get_schema_version()).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    conn.execute(
        """INSERT OR REPLACE INTO query_cache
           (question_hash, question, sql, tier, schema_version, created_at, created_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (question_hash, question, sql, tier, schema_version, now_iso, now_ts),
    )
    conn.commit()


def clear_cache(conn: sqlite3.Connection) -> int:
    """Delete all rows from query_cache.

    Args:
        conn: SQLite connection with query_cache table.

    Returns:
        Number of rows deleted.
    """
    cur = conn.execute("DELETE FROM query_cache")
    conn.commit()
    return cur.rowcount

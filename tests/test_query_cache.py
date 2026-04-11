"""Tests for db_wiki/query/cache.py — NL-to-SQL cache with schema version invalidation."""
import sqlite3
import pytest

from db_wiki.core.query_schema import init_query_schema
from db_wiki.core.store import init_schema
from db_wiki.query.cache import (
    cache_query,
    clear_cache,
    compute_question_hash,
    get_cached_query,
)


@pytest.fixture
def cache_db():
    """In-memory SQLite DB with full schema + query schema initialised."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    init_query_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# compute_question_hash
# ---------------------------------------------------------------------------


def test_compute_question_hash_returns_64_char_hex():
    h = compute_question_hash("show orders")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_question_hash_consistent():
    h1 = compute_question_hash("show orders")
    h2 = compute_question_hash("show orders")
    assert h1 == h2


def test_compute_question_hash_normalises_case_and_whitespace():
    h1 = compute_question_hash("Show Orders")
    h2 = compute_question_hash("  show orders  ")
    assert h1 == h2


def test_compute_question_hash_different_questions_differ():
    h1 = compute_question_hash("show orders")
    h2 = compute_question_hash("show customers")
    assert h1 != h2


# ---------------------------------------------------------------------------
# cache_query + get_cached_query
# ---------------------------------------------------------------------------


def test_cache_and_retrieve_same_schema_version(cache_db):
    q = "show all orders"
    qhash = compute_question_hash(q)
    sql = "SELECT TOP 100 * FROM [Orders]"

    cache_query(cache_db, q, qhash, sql, "lookup", schema_version=5)

    result = get_cached_query(cache_db, qhash, current_schema_version=5)
    assert result == sql


def test_get_cached_query_stale_schema_version_returns_none(cache_db):
    q = "show all orders"
    qhash = compute_question_hash(q)
    sql = "SELECT TOP 100 * FROM [Orders]"

    cache_query(cache_db, q, qhash, sql, "lookup", schema_version=5)

    result = get_cached_query(cache_db, qhash, current_schema_version=6)
    assert result is None


def test_get_cached_query_unknown_hash_returns_none(cache_db):
    result = get_cached_query(cache_db, "nonexistent_hash", current_schema_version=1)
    assert result is None


def test_cache_query_insert_or_replace(cache_db):
    """Re-caching the same hash overwrites the previous entry."""
    q = "show all orders"
    qhash = compute_question_hash(q)

    cache_query(cache_db, q, qhash, "SELECT * FROM [Orders]", "lookup", schema_version=1)
    cache_query(cache_db, q, qhash, "SELECT TOP 100 * FROM [Orders]", "lookup", schema_version=1)

    result = get_cached_query(cache_db, qhash, current_schema_version=1)
    assert result == "SELECT TOP 100 * FROM [Orders]"


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------


def test_clear_cache_deletes_all_rows(cache_db):
    for i in range(3):
        q = f"question {i}"
        qhash = compute_question_hash(q)
        cache_query(cache_db, q, qhash, f"SELECT {i}", "lookup", schema_version=1)

    deleted = clear_cache(cache_db)
    assert deleted == 3

    # All gone
    row = cache_db.execute("SELECT COUNT(*) FROM query_cache").fetchone()
    assert row[0] == 0


def test_clear_cache_empty_table_returns_zero(cache_db):
    assert clear_cache(cache_db) == 0

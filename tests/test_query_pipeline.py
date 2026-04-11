"""Tests for db_wiki/query/pipeline.py — QueryPipeline orchestrator."""
import sqlite3
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from db_wiki.core.config import DBWikiConfig
from db_wiki.core.query_schema import init_query_schema
from db_wiki.core.store import init_schema
from db_wiki.query.classifier import QueryTier
from db_wiki.query.pipeline import QueryPipeline, QueryResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory SQLite with full schema + query schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    init_query_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def config():
    """Default DBWikiConfig (no LLM, no live DB)."""
    return DBWikiConfig()


@pytest.fixture
def llm_config():
    """DBWikiConfig with LLM provider configured."""
    cfg = DBWikiConfig()
    cfg.learning.llm_provider = "claude"
    cfg.learning.llm_api_key = "test-key"
    return cfg


# ---------------------------------------------------------------------------
# Helpers for mocking pipeline internals
# ---------------------------------------------------------------------------

_MOCK_CONTEXT = MagicMock()
_MOCK_CONTEXT.text = "Table: Orders\n  id INT\n  status VARCHAR"
_MOCK_CONTEXT.token_count = 50
_MOCK_CONTEXT.l0_count = 1
_MOCK_CONTEXT.l1_count = 0
_MOCK_CONTEXT.l2_count = 0

_GOOD_SQL = "SELECT TOP 100 * FROM [Orders]"
_BAD_SQL = "SELECT * FROM NonExistentTable"


def _make_gen_result(sql, from_template=True):
    from db_wiki.query.generator import GenerationResult
    return GenerationResult(sql=sql, prompt_used="", from_template=from_template)


# ---------------------------------------------------------------------------
# QueryResult dataclass
# ---------------------------------------------------------------------------


def test_query_result_defaults():
    r = QueryResult(question="q", tier="lookup", sql=None)
    assert r.validation_errors == []
    assert r.attempts == 0
    assert r.from_cache is False
    assert r.context_tokens == 0
    assert r.execution_result is None


# ---------------------------------------------------------------------------
# QueryPipeline construction
# ---------------------------------------------------------------------------


def test_pipeline_construction(db, config):
    """Pipeline initialises without errors on empty DB."""
    pipeline = QueryPipeline(db, config)
    assert pipeline is not None


# ---------------------------------------------------------------------------
# Cache hit path
# ---------------------------------------------------------------------------


def test_run_cache_hit_returns_cached_sql(db, config):
    """Second call with same question returns from_cache=True."""
    from db_wiki.query.cache import cache_query, compute_question_hash

    question = "show all orders"
    qhash = compute_question_hash(question)
    cache_query(db, question, qhash, _GOOD_SQL, "lookup", schema_version=0)

    pipeline = QueryPipeline(db, config)
    result = pipeline.run(question)

    assert result.from_cache is True
    assert result.sql == _GOOD_SQL


def test_run_cache_miss_proceeds_to_generate(db, config):
    """No cache entry → pipeline runs generation."""
    pipeline = QueryPipeline(db, config)

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.LOOKUP),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(_GOOD_SQL)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
    ):
        result = pipeline.run("show all orders")

    assert result.from_cache is False
    assert result.sql == _GOOD_SQL


# ---------------------------------------------------------------------------
# Single-pass success path
# ---------------------------------------------------------------------------


def test_run_single_pass_lookup_success(db, config):
    """Lookup tier single-pass returns sql and tier=lookup, attempts=1."""
    pipeline = QueryPipeline(db, config)

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.LOOKUP),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(_GOOD_SQL)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
    ):
        result = pipeline.run("show all orders")

    assert result.sql == _GOOD_SQL
    assert result.tier == "lookup"
    assert result.attempts == 1
    assert result.validation_errors == []


# ---------------------------------------------------------------------------
# Retry path (self-correcting loop)
# ---------------------------------------------------------------------------


def test_run_retries_on_validation_error(db, config):
    """Validation fails first attempt, succeeds second — attempts=2."""
    pipeline = QueryPipeline(db, config)

    gen_calls = []

    def mock_generate(question, tier, context_text, cfg, metrics=None, previous_error=None):
        gen_calls.append(previous_error)
        if previous_error is None:
            return _make_gen_result(_BAD_SQL)
        return _make_gen_result(_GOOD_SQL)

    validate_calls = []

    def mock_validate(sql, schema_map):
        validate_calls.append(sql)
        if sql == _BAD_SQL:
            return ["Unknown table: NonExistentTable"]
        return []

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.LOOKUP),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", side_effect=mock_generate),
        patch("db_wiki.query.pipeline.validate_sql", side_effect=mock_validate),
    ):
        result = pipeline.run("show nonexistent table")

    assert result.sql == _GOOD_SQL
    assert result.attempts == 2
    assert result.validation_errors == []
    # Second generation received the error from first attempt
    assert gen_calls[1] is not None
    assert "NonExistentTable" in gen_calls[1]


def test_run_respects_max_retries(db, config):
    """Generation always fails validation — stops at max_retries attempts."""
    config.query.max_retries = 2
    pipeline = QueryPipeline(db, config)

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.LOOKUP),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(_BAD_SQL)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=["error"]),
    ):
        result = pipeline.run("broken query")

    assert result.attempts == 2
    assert result.validation_errors == ["error"]


# ---------------------------------------------------------------------------
# Template returns None for tier 3+
# ---------------------------------------------------------------------------


def test_run_tier3_no_llm_returns_none_sql(db, config):
    """Tier 3+ (TEMPORAL) with no LLM — template returns None sql."""
    pipeline = QueryPipeline(db, config)

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.TEMPORAL),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(None)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
    ):
        result = pipeline.run("orders from last month")

    assert result.sql is None
    assert result.tier == "temporal"


# ---------------------------------------------------------------------------
# Analyst Agent path (tier 3+ with LLM)
# ---------------------------------------------------------------------------


def test_run_analyst_path_tier3_with_llm(db, llm_config):
    """Tier 3+ with LLM configured — AnalystAgent.decompose is called."""
    pipeline = QueryPipeline(db, llm_config)

    sub_sql = "SELECT id FROM Orders WHERE created_at >= DATEADD(month, -1, GETDATE())"
    composed_sql = "WITH cte AS (SELECT id FROM Orders WHERE created_at >= DATEADD(month, -1, GETDATE())) SELECT * FROM cte"

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.TEMPORAL),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(sub_sql)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
        patch.object(pipeline._analyst, "decompose", return_value=["sub q 1", "sub q 2"]),
        patch.object(pipeline._analyst, "compose", return_value=composed_sql),
    ):
        result = pipeline.run("find orders with missing emails from last month")

    # Analyst path was taken → composed SQL returned
    assert result.sql == composed_sql
    assert result.tier == "temporal"


def test_run_analyst_offline_fallback_no_llm(db, config):
    """Tier 3+ with no LLM — decompose returns [original_question], pipeline falls through to single-pass."""
    pipeline = QueryPipeline(db, config)

    # No LLM → decompose returns [original_question] → not in analyst tiers path
    # Pipeline goes directly to single-pass, template returns None for temporal
    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.TEMPORAL),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(None)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
    ):
        result = pipeline.run("orders from last month")

    # Single-pass for TEMPORAL with no LLM → template returns None
    assert result.sql is None
    assert result.tier == "temporal"


# ---------------------------------------------------------------------------
# Execute path
# ---------------------------------------------------------------------------


def test_run_with_execute_true_includes_execution_result(db, config):
    """execute=True adds execution_result to QueryResult."""
    pipeline = QueryPipeline(db, config)

    mock_exec_result = {"success": False, "rows": None, "error": "No database connection configured", "row_count": 0}

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.LOOKUP),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(_GOOD_SQL)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
        patch("db_wiki.query.pipeline.execute_query", return_value=mock_exec_result),
    ):
        result = pipeline.run("show orders", execute=True)

    assert result.execution_result is not None
    assert result.execution_result["success"] is False


def test_run_execute_false_no_execution_result(db, config):
    """execute=False (default) leaves execution_result=None."""
    pipeline = QueryPipeline(db, config)

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.LOOKUP),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(_GOOD_SQL)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
    ):
        result = pipeline.run("show orders")

    assert result.execution_result is None


# ---------------------------------------------------------------------------
# Cache write after successful generation
# ---------------------------------------------------------------------------


def test_run_caches_successful_result(db, config):
    """Pipeline writes result to cache after successful generation."""
    pipeline = QueryPipeline(db, config)

    with (
        patch("db_wiki.query.pipeline.classify_query", return_value=QueryTier.LOOKUP),
        patch("db_wiki.query.pipeline.resolve_concepts", return_value=[]),
        patch("db_wiki.query.pipeline.assemble_context", return_value=_MOCK_CONTEXT),
        patch("db_wiki.query.pipeline.get_all_metrics", return_value=[]),
        patch("db_wiki.query.pipeline.generate_sql", return_value=_make_gen_result(_GOOD_SQL)),
        patch("db_wiki.query.pipeline.validate_sql", return_value=[]),
    ):
        pipeline.run("show all orders")

    # Run again — should now be a cache hit
    result2 = pipeline.run("show all orders")
    assert result2.from_cache is True
    assert result2.sql == _GOOD_SQL

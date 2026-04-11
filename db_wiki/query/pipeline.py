"""QueryPipeline — full NL-to-SQL orchestrator.

Chains all Phase 4 query engine modules into a single entry point:
  classify -> resolve -> join_paths -> context -> generate -> validate -> retry
  + cache (read/write)
  + optional analyst decomposition for tier 3+ queries
  + optional live DB execution

Security note (T-04-07): SQL is never executed by default. The caller must
pass execute=True explicitly. The executor enforces SELECT-only at that point.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field

from db_wiki.query.analyst import AnalystAgent
from db_wiki.query.cache import (
    cache_query,
    compute_question_hash,
    get_cached_query,
)
from db_wiki.query.classifier import QueryTier, classify_query
from db_wiki.query.context import assemble_context
from db_wiki.query.executor import execute_query
from db_wiki.query.generator import generate_sql
from db_wiki.query.resolver import (
    get_all_metrics,
    get_schema_version,
    resolve_concepts,
)
from db_wiki.query.validator import build_schema_map, validate_sql

logger = logging.getLogger(__name__)

# Tiers that benefit from Analyst Agent decomposition (tier 3+)
_ANALYST_TIERS = {
    QueryTier.TEMPORAL,
    QueryTier.STATISTICAL,
    QueryTier.FORENSIC,
    QueryTier.DATA_QUALITY,
}


@dataclass
class QueryResult:
    """Result of a QueryPipeline.run() call."""

    question: str
    tier: str
    sql: str | None
    validation_errors: list[str] = field(default_factory=list)
    attempts: int = 0
    from_cache: bool = False
    context_tokens: int = 0
    execution_result: dict | None = None


class QueryPipeline:
    """Orchestrates the full NL-to-SQL pipeline.

    Usage:
        pipeline = QueryPipeline(conn, config)
        result = pipeline.run("show all orders with missing emails")
        print(result.sql)
    """

    def __init__(self, conn: sqlite3.Connection, config) -> None:
        """Initialise with SQLite connection and DBWikiConfig.

        Args:
            conn: Open SQLite connection to the knowledge store (must have
                  full schema + Phase 4 query schema initialised).
            config: DBWikiConfig instance.
        """
        self._conn = conn
        self._config = config
        self._analyst = AnalystAgent(config)
        self._schema_map = build_schema_map(conn)

    def run(self, question: str, execute: bool = False) -> QueryResult:
        """Run the full NL-to-SQL pipeline for the given question.

        Steps:
          1. Cache check (if cache_enabled)
          2. Classify question into a QueryTier
          3. For tier 3+ with LLM: use AnalystAgent to decompose + compose
          4. For tier 1-2 or no LLM: single-pass _single_pass()
          5. Cache successful result (if cache_enabled)
          6. Execute if requested and sql is not None

        Args:
            question: The natural language question to answer.
            execute: Whether to execute the generated SQL against the live DB.
                     Requires config.database.connection_string to be set.

        Returns:
            QueryResult with all pipeline outputs.
        """
        cache_enabled = getattr(
            getattr(self._config, "query", None), "cache_enabled", True
        )

        # Step 1: Cache check
        if cache_enabled:
            question_hash = compute_question_hash(question)
            schema_ver = get_schema_version(self._conn)
            cached_sql = get_cached_query(self._conn, question_hash, schema_ver)
            if cached_sql is not None:
                result = QueryResult(
                    question=question,
                    tier="cached",
                    sql=cached_sql,
                    from_cache=True,
                    attempts=0,
                )
                if execute and cached_sql:
                    result.execution_result = execute_query(cached_sql, self._config)
                return result

        # Step 2: Classify
        tier = classify_query(question, self._config)

        # Step 3: Analyst Agent for tier 3+ when LLM is configured
        llm_provider = getattr(
            getattr(self._config, "learning", None), "llm_provider", None
        )
        final_result: QueryResult | None = None

        if tier in _ANALYST_TIERS and llm_provider:
            final_result = self._analyst_pass(question, tier)

        # Step 4: Single-pass fallback (tier 1-2 or no LLM or analyst failed)
        if final_result is None or (final_result.sql is None and not final_result.validation_errors):
            final_result = self._single_pass(question, tier)

        # Step 5: Cache successful result
        if cache_enabled and final_result.sql is not None and not final_result.validation_errors:
            qhash = compute_question_hash(question)
            schema_ver = get_schema_version(self._conn)
            try:
                cache_query(
                    self._conn,
                    question,
                    qhash,
                    final_result.sql,
                    final_result.tier,
                    schema_ver,
                )
            except Exception:
                logger.warning("Failed to cache query result", exc_info=True)

        # Step 6: Execute if requested
        if execute and final_result.sql is not None:
            final_result.execution_result = execute_query(final_result.sql, self._config)

        return final_result

    def _analyst_pass(self, question: str, tier: QueryTier) -> QueryResult | None:
        """Attempt Analyst Agent decomposition for tier 3+ queries.

        Args:
            question: The NL question.
            tier: The classified QueryTier.

        Returns:
            QueryResult if analyst succeeded, None if it should fall through to
            single-pass.
        """
        try:
            sub_questions = self._analyst.decompose(question, tier.value)

            # If decompose returned only the original question, no decomposition occurred
            if sub_questions == [question]:
                return None

            # Run single-pass on each sub-question
            sub_results = [self._single_pass(sq, tier) for sq in sub_questions]

            # Compose sub-results into unified SQL
            final_sql = self._analyst.compose(sub_results, question)

            if final_sql is None:
                return None

            # Validate the composed SQL
            errors = validate_sql(final_sql, self._schema_map)
            if errors:
                logger.debug("Analyst composed SQL failed validation: %s", errors)
                return None  # Fall through to single-pass

            # Collect token counts from sub-results
            total_tokens = sum(r.context_tokens for r in sub_results)

            return QueryResult(
                question=question,
                tier=tier.value,
                sql=final_sql,
                validation_errors=[],
                attempts=sum(r.attempts for r in sub_results),
                from_cache=False,
                context_tokens=total_tokens,
            )

        except Exception:
            logger.warning("AnalystAgent pass failed", exc_info=True)
            return None

    def _single_pass(self, question: str, tier: QueryTier) -> QueryResult:
        """Run the classify→resolve→context→generate→validate loop for one question.

        Args:
            question: The NL question (may be a sub-question from decomposition).
            tier: The QueryTier to use for generation.

        Returns:
            QueryResult.
        """
        max_retries = getattr(
            getattr(self._config, "query", None), "max_retries", 3
        )
        token_budget = getattr(
            getattr(self._config, "query", None), "token_budget", 8000
        )

        # Resolve concepts to entity IDs
        try:
            entities = resolve_concepts(self._conn, question, self._config.embedding)
        except Exception:
            logger.warning("resolve_concepts failed", exc_info=True)
            entities = []

        # Split into core (table) and related entity IDs
        table_entities = [e for e in entities if e.entity_type == "table"]
        core_ids = [e.entity_id for e in table_entities[:5]]
        related_ids: list[int] = []

        # Add non-table entities as related
        other_entities = [e for e in entities if e.entity_type != "table"]
        related_ids = [e.entity_id for e in other_entities[:10]]

        # Assemble context
        try:
            ctx = assemble_context(
                self._conn, core_ids, related_ids, token_budget
            )
        except Exception:
            logger.warning("assemble_context failed", exc_info=True)
            from db_wiki.query.context import ContextResult
            ctx = ContextResult(text="", token_count=0, l0_count=0, l1_count=0, l2_count=0)

        # Get all metrics for use in generation prompt
        try:
            metrics = get_all_metrics(self._conn)
            metrics_list = [
                {"name": m.name, "formula": m.sql_fragment}
                for m in metrics
            ]
        except Exception:
            metrics_list = []

        # Generate + validate loop with self-correction
        gen_sql: str | None = None
        errors: list[str] = []
        attempts = 0
        previous_error: str | None = None

        for attempt in range(max_retries):
            attempts = attempt + 1
            try:
                gen = generate_sql(
                    question,
                    tier.value,
                    ctx.text,
                    self._config,
                    metrics=metrics_list if metrics_list else None,
                    previous_error=previous_error,
                )
            except Exception:
                logger.warning("generate_sql failed on attempt %d", attempts, exc_info=True)
                break

            if gen.sql is None:
                # Template cannot handle this tier (requires LLM)
                gen_sql = None
                errors = []
                break

            # Validate the generated SQL
            errors = validate_sql(gen.sql, self._schema_map)
            if not errors:
                gen_sql = gen.sql
                break

            # Prepare error feedback for next attempt
            previous_error = "; ".join(errors)
            logger.debug(
                "SQL validation failed on attempt %d: %s", attempts, previous_error
            )

        return QueryResult(
            question=question,
            tier=tier.value,
            sql=gen_sql,
            validation_errors=errors,
            attempts=attempts,
            from_cache=False,
            context_tokens=ctx.token_count,
        )
